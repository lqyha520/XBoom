<?php
/**
 * 接收客户端启动上报，记录公网 IP 到 MySQL（库 XBoom）
 * POST JSON: { "install_id": "uuid", "app_version": "1.0.2", "os_platform": "Windows-10" }
 */
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, X-Stats-Token');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'method_not_allowed']);
    exit;
}

$configPath = __DIR__ . '/config.php';
if (!is_file($configPath)) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'server_not_configured']);
    exit;
}

/** @var array<string, mixed> $cfg */
$cfg = require $configPath;

$token = (string)($cfg['report_token'] ?? '');
if ($token !== '') {
    $sent = $_SERVER['HTTP_X_STATS_TOKEN'] ?? '';
    if (!hash_equals($token, (string)$sent)) {
        http_response_code(403);
        echo json_encode(['ok' => false, 'error' => 'forbidden']);
        exit;
    }
}

function client_ip(): string
{
    $xff = $_SERVER['HTTP_X_FORWARDED_FOR'] ?? '';
    if ($xff !== '') {
        $parts = array_map('trim', explode(',', $xff));
        if ($parts[0] !== '') {
            return substr($parts[0], 0, 45);
        }
    }
    $real = $_SERVER['HTTP_X_REAL_IP'] ?? '';
    if ($real !== '') {
        return substr(trim($real), 0, 45);
    }
    return substr((string)($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0'), 0, 45);
}

function rate_limit_ok(PDO $pdo, string $ip, int $limit): bool
{
    if ($limit <= 0) {
        return true;
    }
    $stmt = $pdo->prepare(
        'SELECT COUNT(*) FROM usage_visits WHERE ip = ? AND created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)'
    );
    $stmt->execute([$ip]);
    $count = (int)$stmt->fetchColumn();
    return $count < $limit;
}

$raw = file_get_contents('php://input') ?: '';
$data = json_decode($raw, true);
if (!is_array($data)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'invalid_json']);
    exit;
}

$installId = strtolower(trim((string)($data['install_id'] ?? '')));
if (!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i', $installId)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'invalid_install_id']);
    exit;
}

$appVersion = substr(trim((string)($data['app_version'] ?? '')), 0, 32);
$osPlatform = substr(trim((string)($data['os_platform'] ?? '')), 0, 64);
$ip = client_ip();

try {
    $dsn = sprintf(
        'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
        $cfg['db_host'] ?? '127.0.0.1',
        (int)($cfg['db_port'] ?? 3306),
        $cfg['db_name'] ?? 'XBoom'
    );
    $pdo = new PDO($dsn, (string)($cfg['db_user'] ?? 'root'), (string)($cfg['db_pass'] ?? ''), [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'db_connect_failed']);
    exit;
}

$rateLimit = (int)($cfg['rate_limit_per_hour'] ?? 30);
if (!rate_limit_ok($pdo, $ip, $rateLimit)) {
    http_response_code(429);
    echo json_encode(['ok' => false, 'error' => 'rate_limited']);
    exit;
}

try {
    $pdo->beginTransaction();

    $pdo->prepare(
        'INSERT INTO usage_visits (install_id, ip, app_version, os_platform) VALUES (?, ?, ?, ?)'
    )->execute([$installId, $ip, $appVersion, $osPlatform]);

    $exists = $pdo->prepare('SELECT install_id FROM usage_users WHERE install_id = ? LIMIT 1');
    $exists->execute([$installId]);
    if ($exists->fetch()) {
        $pdo->prepare(
            'UPDATE usage_users SET last_ip = ?, last_seen = NOW(), visit_count = visit_count + 1,
             app_version = ?, os_platform = ? WHERE install_id = ?'
        )->execute([$ip, $appVersion, $osPlatform, $installId]);
    } else {
        $pdo->prepare(
            'INSERT INTO usage_users
             (install_id, first_ip, last_ip, first_seen, last_seen, visit_count, app_version, os_platform)
             VALUES (?, ?, ?, NOW(), NOW(), 1, ?, ?)'
        )->execute([$installId, $ip, $ip, $appVersion, $osPlatform]);
    }

    $pdo->commit();
} catch (Throwable $e) {
    if ($pdo->inTransaction()) {
        $pdo->rollBack();
    }
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'db_write_failed']);
    exit;
}

echo json_encode(['ok' => true, 'ip' => $ip]);

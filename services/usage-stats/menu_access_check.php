<?php
/**
 * 白名单菜单可见性检查接口（客户端无需数据库账号密码）
 * GET /menu_access_check.php
 */
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, X-Stats-Token');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
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

try {
    $stmt = $pdo->prepare('SELECT COUNT(*) FROM menu_ip_whitelist WHERE enabled = 1');
    $stmt->execute();
    $count = (int)$stmt->fetchColumn();

    $stmt = $pdo->prepare('SELECT 1 FROM menu_ip_whitelist WHERE ip = ? AND enabled = 1 LIMIT 1');
    $stmt->execute([$ip]);
    $allowed = (bool)$stmt->fetchColumn();
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'db_query_failed']);
    exit;
}

echo json_encode([
    'ok' => true,
    'ip' => $ip,
    'allowed' => $allowed,
    'whitelist_count' => $count,
    'message' => $allowed
        ? "本机 IP {$ip} 在白名单中（共 {$count} 条）"
        : "本机 IP {$ip} 不在白名单（库内 {$count} 条）",
]);

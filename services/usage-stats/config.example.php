<?php
/**
 * 复制为 config.php 后填写（勿提交 config.php）
 */
return [
    'db_host' => 'localhost',
    'db_port' => 3306,
    'db_name' => 'XBoom',
    'db_user' => 'root',
    'db_pass' => '在此填写MySQL密码',
    // 可选：非空时客户端须在请求头带 X-Stats-Token
    'report_token' => '',
    // 同一 IP 每小时最多上报次数（防刷）
    'rate_limit_per_hour' => 30,
];

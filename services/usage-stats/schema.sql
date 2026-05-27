-- 小爆来咯 使用统计库（宝塔 MySQL 执行）
-- 用法：宝塔 → 数据库 → 导入，或 ssh 执行: mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS `XBoom`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `XBoom`;

-- 每次启动上报一条访问记录（含 IP）
CREATE TABLE IF NOT EXISTS `usage_visits` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `install_id` CHAR(36) NOT NULL COMMENT '客户端匿名安装 ID',
  `ip` VARCHAR(45) NOT NULL COMMENT '公网 IP',
  `app_version` VARCHAR(32) NOT NULL DEFAULT '',
  `os_platform` VARCHAR(64) NOT NULL DEFAULT '',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_install_id` (`install_id`),
  KEY `idx_ip` (`ip`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='每次启动上报';

-- 按安装 ID 汇总（去重统计「有多少台在用」）
CREATE TABLE IF NOT EXISTS `usage_users` (
  `install_id` CHAR(36) NOT NULL,
  `first_ip` VARCHAR(45) NOT NULL,
  `last_ip` VARCHAR(45) NOT NULL,
  `first_seen` DATETIME NOT NULL,
  `last_seen` DATETIME NOT NULL,
  `visit_count` INT UNSIGNED NOT NULL DEFAULT 1,
  `app_version` VARCHAR(32) NOT NULL DEFAULT '',
  `os_platform` VARCHAR(64) NOT NULL DEFAULT '',
  PRIMARY KEY (`install_id`),
  KEY `idx_last_ip` (`last_ip`),
  KEY `idx_last_seen` (`last_seen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='安装维度汇总';

-- 受限菜单 IP 白名单（工作台 / 知识库 / 任务监控 / 素材中心）
-- 客户端启动时读取 enabled=1 的记录，与本机公网 IP 比对
CREATE TABLE IF NOT EXISTS `menu_ip_whitelist` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `ip` VARCHAR(45) NOT NULL COMMENT '客户端公网 IP',
  `remark` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '备注',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1=生效 0=停用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ip` (`ip`),
  KEY `idx_enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='受限菜单可见 IP 白名单';

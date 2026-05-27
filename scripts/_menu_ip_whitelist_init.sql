USE `XBoom`;

CREATE TABLE IF NOT EXISTS `menu_ip_whitelist` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `ip` VARCHAR(45) NOT NULL COMMENT 'client public ip',
  `remark` VARCHAR(128) NOT NULL DEFAULT '',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ip` (`ip`),
  KEY `idx_enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `menu_ip_whitelist` (`ip`, `remark`, `enabled`)
VALUES ('153.121.40.248', 'admin-local', 1)
ON DUPLICATE KEY UPDATE `remark`=VALUES(`remark`), `enabled`=1;

SELECT * FROM `menu_ip_whitelist`;

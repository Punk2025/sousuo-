-- 阶段 B 结果表（MySQL）
-- SQLite 版由程序自动建表，字段对齐。

CREATE TABLE IF NOT EXISTS serp_results (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  keyword VARCHAR(255) NOT NULL,
  rank_no INT NULL,
  serp_url TEXT NOT NULL,
  title VARCHAR(512) NULL,
  fetched_at VARCHAR(64) NULL,
  final_url TEXT NULL,
  is_js_redirect TINYINT(1) DEFAULT 0,
  jump_script TEXT NULL,
  page_type VARCHAR(64) NULL,
  tags_json JSON NULL,
  has_tg TINYINT(1) DEFAULT 0,
  has_usdt TINYINT(1) DEFAULT 0,
  has_gambling TINYINT(1) DEFAULT 0,
  has_adult TINYINT(1) DEFAULT 0,
  confidence DECIMAL(4,3) NULL,
  evidence TEXT NULL,
  raw_excerpt TEXT NULL,
  processed_at DATETIME NULL,
  UNIQUE KEY uk_keyword_serp (keyword(191), serp_url(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

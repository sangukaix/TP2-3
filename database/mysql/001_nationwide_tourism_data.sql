-- STAY-UP AI 관광 관측값·출처·ML artifact를 저장하는 MySQL 8.x schema다.
-- staging 검증과 공식 지역코드 승인이 끝난 데이터만 이 테이블에 적재한다.

CREATE TABLE IF NOT EXISTS dim_region (
    region_code VARCHAR(10) PRIMARY KEY COMMENT '공식 시군구 지역코드',
    province_name VARCHAR(50) NOT NULL,
    municipality_name VARCHAR(50) NOT NULL,
    local_hierarchy_name VARCHAR(100) NOT NULL,
    valid_from DATE NULL,
    valid_to DATE NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE KEY uq_region_official_name (province_name, local_hierarchy_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 원본 ZIP 한 개를 한 source로 등록해 모든 수치가 원본까지 추적되게 한다.
CREATE TABLE IF NOT EXISTS data_source (
    source_id VARCHAR(80) PRIMARY KEY,
    source_name VARCHAR(200) NOT NULL,
    source_page_url TEXT NULL,
    downloaded_at DATETIME NULL,
    file_name VARCHAR(500) NOT NULL,
    file_hash CHAR(64) NOT NULL,
    date_range VARCHAR(30) NULL,
    geographic_level VARCHAR(30) NOT NULL,
    filters_json JSON NULL,
    methodology_notes TEXT NULL,
    review_status VARCHAR(30) NOT NULL,
    UNIQUE KEY uq_data_source_file (file_hash, file_name(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 적재 실행별 원본·정상·거절 행 수를 보존해 누락 여부를 검증한다.
CREATE TABLE IF NOT EXISTS data_load_run (
    load_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    raw_snapshot VARCHAR(200) NOT NULL,
    inventory_hash CHAR(64) NOT NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME NULL,
    status VARCHAR(30) NOT NULL,
    source_file_count INT UNSIGNED NOT NULL DEFAULT 0,
    raw_row_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    loaded_row_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    filtered_row_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    rejected_row_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    CHECK (status IN ('running', 'validated', 'failed', 'rolled_back'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS data_load_rejection (
    rejection_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    load_run_id BIGINT UNSIGNED NOT NULL,
    source_id VARCHAR(80) NULL,
    -- ROW_NUMBER는 MySQL 8의 윈도 함수 이름이므로, 일반 열 이름으로 사용하지 않습니다.
    source_row_index INT UNSIGNED NULL,
    raw_region_key VARCHAR(150) NULL,
    raw_year_month VARCHAR(30) NULL,
    error_code VARCHAR(60) NOT NULL,
    detail TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_rejection_run FOREIGN KEY (load_run_id) REFERENCES data_load_run(load_run_id),
    CONSTRAINT fk_rejection_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    KEY ix_rejection_run_code (load_run_id, error_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 계산되지 않은 공식 월별 관측값만 저장한다. 파생 지표는 별도 view/API에서 계산한다.
CREATE TABLE IF NOT EXISTS fact_tourism_monthly (
    region_code VARCHAR(10) NOT NULL,
    -- YEAR_MONTH는 MySQL interval 키워드이므로 인용해 일반 식별자로 사용합니다.
    `year_month` CHAR(7) NOT NULL COMMENT 'YYYY-MM',
    visitors BIGINT UNSIGNED NULL,
    visitors_previous_year BIGINT UNSIGNED NULL,
    visitors_yoy_pct DECIMAL(10,4) NULL,
    domestic_tourism_spend_thousand_krw DECIMAL(22,3) NULL,
    nonlocal_tourism_spend_thousand_krw DECIMAL(22,3) NULL,
    unique_visitors BIGINT UNSIGNED NULL,
    overnight_ratio_pct DECIMAL(10,4) NULL,
    avg_stay_days DECIMAL(10,4) NULL,
    avg_stay_minutes DECIMAL(14,4) NULL,
    data_status VARCHAR(20) NOT NULL,
    load_run_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (region_code, `year_month`),
    CONSTRAINT fk_monthly_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    CONSTRAINT fk_monthly_load_run FOREIGN KEY (load_run_id) REFERENCES data_load_run(load_run_id),
    CHECK (`year_month` REGEXP '^20[0-9]{2}-(0[1-9]|1[0-2])$'),
    CHECK (data_status IN ('complete', 'partial')),
    KEY ix_monthly_period (`year_month`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 하나의 월별 행에서 각 metric이 어느 ZIP에서 왔는지 정규화해 저장한다.
CREATE TABLE IF NOT EXISTS fact_tourism_metric_source (
    region_code VARCHAR(10) NOT NULL,
    `year_month` CHAR(7) NOT NULL,
    metric_name VARCHAR(80) NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (region_code, `year_month`, metric_name),
    CONSTRAINT fk_metric_source_fact FOREIGN KEY (region_code, `year_month`)
        REFERENCES fact_tourism_monthly(region_code, `year_month`) ON DELETE CASCADE,
    CONSTRAINT fk_metric_source_source FOREIGN KEY (source_id) REFERENCES data_source(source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 기획안의 지역 비교는 원본 월별 사실과 분리한 재현 가능한 12개월 요약만 사용한다.
-- 이 표는 정책 효과를 저장하지 않으며, 관측된 기간 비교·백분위·동일 정의의 peer만 보관한다.
CREATE TABLE IF NOT EXISTS regional_planning_context (
    region_code VARCHAR(10) PRIMARY KEY,
    period_start CHAR(7) NOT NULL,
    period_end CHAR(7) NOT NULL,
    comparison_period_start CHAR(7) NOT NULL,
    comparison_period_end CHAR(7) NOT NULL,
    visitors_12m BIGINT UNSIGNED NOT NULL,
    visitors_yoy_pct DECIMAL(12,6) NULL,
    domestic_spend_12m_thousand_krw DECIMAL(24,4) NULL,
    domestic_spend_yoy_pct DECIMAL(12,6) NULL,
    spend_per_visitor_krw DECIMAL(18,4) NULL,
    overnight_ratio_avg_pct DECIMAL(12,6) NULL,
    avg_stay_days DECIMAL(12,6) NULL,
    avg_stay_minutes DECIMAL(16,6) NULL,
    peak_calendar_month TINYINT UNSIGNED NULL,
    observed_month_count SMALLINT UNSIGNED NOT NULL,
    data_quality_status VARCHAR(50) NOT NULL,
    source_ids_json JSON NOT NULL,
    visitors_12m_percentile DECIMAL(8,4) NULL,
    spend_per_visitor_krw_percentile DECIMAL(8,4) NULL,
    overnight_ratio_avg_pct_percentile DECIMAL(8,4) NULL,
    avg_stay_days_percentile DECIMAL(8,4) NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_planning_context_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    CHECK (period_start REGEXP '^20[0-9]{2}-(0[1-9]|1[0-2])$'),
    CHECK (period_end REGEXP '^20[0-9]{2}-(0[1-9]|1[0-2])$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 비교 지역은 표준화된 관측 지표 거리로 계산한 참고 집단이다. 전국 평균으로 해석하지 않는다.
CREATE TABLE IF NOT EXISTS regional_peer_comparison (
    region_code VARCHAR(10) NOT NULL,
    peer_rank SMALLINT UNSIGNED NOT NULL,
    peer_region_code VARCHAR(10) NOT NULL,
    distance DECIMAL(16,8) NOT NULL,
    visitors_gap_pct DECIMAL(12,6) NULL,
    spend_per_visitor_gap_krw DECIMAL(18,4) NULL,
    overnight_ratio_gap_pct_point DECIMAL(12,6) NULL,
    comparison_period_end CHAR(7) NOT NULL,
    method VARCHAR(80) NOT NULL,
    PRIMARY KEY (region_code, peer_rank),
    CONSTRAINT fk_peer_selected_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    CONSTRAINT fk_peer_region FOREIGN KEY (peer_region_code) REFERENCES dim_region(region_code),
    CHECK (comparison_period_end REGEXP '^20[0-9]{2}-(0[1-9]|1[0-2])$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 기획안의 기대 변화는 정책 효과 예측이 아니라 사후 측정 계획으로 관리한다.
-- baseline과 follow-up을 분리해 저장하면 사용자 목표·실제 관측값·기간을 혼동하지 않는다.
CREATE TABLE IF NOT EXISTS strategy_measurement_baseline (
    report_id VARCHAR(64) NOT NULL,
    region_code VARCHAR(10) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    baseline_month CHAR(7) NOT NULL,
    observed_value DECIMAL(24,4) NOT NULL,
    unit VARCHAR(40) NOT NULL,
    source_references_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (report_id, metric_name),
    KEY ix_measurement_baseline_region (region_code, baseline_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS strategy_measurement_followup (
    followup_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    report_id VARCHAR(64) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    observed_month CHAR(7) NOT NULL,
    observed_value DECIMAL(24,4) NOT NULL,
    unit VARCHAR(40) NOT NULL,
    source_references_json JSON NOT NULL,
    recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_measurement_followup (report_id, metric_name, observed_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 모델 파일과 평가·feature·학습 snapshot을 함께 등록해 재현성을 보장한다.
CREATE TABLE IF NOT EXISTS ml_model_registry (
    model_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    target_name VARCHAR(80) NOT NULL,
    model_version VARCHAR(80) NOT NULL,
    model_type VARCHAR(100) NOT NULL,
    artifact_path VARCHAR(500) NOT NULL,
    artifact_sha256 CHAR(64) NOT NULL,
    training_start_month CHAR(7) NOT NULL,
    training_end_month CHAR(7) NOT NULL,
    evaluation_json JSON NOT NULL,
    feature_schema_json JSON NOT NULL,
    training_manifest_json JSON NOT NULL,
    decision_status VARCHAR(30) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_model_version (target_name, model_version),
    CHECK (decision_status IN ('decision_usable', 'baseline_only', 'experimental', 'rejected'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ml_prediction (
    prediction_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    model_id BIGINT UNSIGNED NOT NULL,
    region_code VARCHAR(10) NOT NULL,
    target_month CHAR(7) NOT NULL,
    horizon_months SMALLINT UNSIGNED NOT NULL,
    predicted_value DECIMAL(22,4) NOT NULL,
    lower_bound DECIMAL(22,4) NULL,
    upper_bound DECIMAL(22,4) NULL,
    prediction_status VARCHAR(30) NOT NULL,
    feature_snapshot_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_prediction_model FOREIGN KEY (model_id) REFERENCES ml_model_registry(model_id),
    CONSTRAINT fk_prediction_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    UNIQUE KEY uq_prediction (model_id, region_code, target_month, horizon_months),
    KEY ix_prediction_region_month (region_code, target_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 관광지 방문객 표에 공식 ID가 없을 때 name hash를 사용하고, 추후 공식 ID를 연결한다.
CREATE TABLE IF NOT EXISTS dim_attraction (
    attraction_key VARCHAR(64) PRIMARY KEY,
    official_attraction_id VARCHAR(80) NULL,
    region_code VARCHAR(10) NOT NULL,
    attraction_name VARCHAR(250) NOT NULL,
    category_large VARCHAR(100) NULL,
    category_middle VARCHAR(100) NULL,
    mapping_status VARCHAR(30) NOT NULL,
    CONSTRAINT fk_attraction_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    UNIQUE KEY uq_attraction_official_id (official_attraction_id),
    UNIQUE KEY uq_attraction_region_name (region_code, attraction_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fact_attraction_monthly_visitors (
    attraction_key VARCHAR(64) NOT NULL,
    visitor_type VARCHAR(20) NOT NULL,
    `year_month` CHAR(7) NOT NULL,
    visitors BIGINT UNSIGNED NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    load_run_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (attraction_key, visitor_type, `year_month`),
    CONSTRAINT fk_attraction_monthly_dim FOREIGN KEY (attraction_key) REFERENCES dim_attraction(attraction_key),
    CONSTRAINT fk_attraction_monthly_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    CONSTRAINT fk_attraction_monthly_load FOREIGN KEY (load_run_id) REFERENCES data_load_run(load_run_id),
    CHECK (visitor_type IN ('내국인', '외국인')),
    KEY ix_attraction_month (`year_month`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS attraction_edge (
    center_attraction_key VARCHAR(64) NOT NULL,
    related_attraction_key VARCHAR(64) NOT NULL,
    rank_no SMALLINT UNSIGNED NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (center_attraction_key, related_attraction_key, source_id),
    CONSTRAINT fk_edge_center FOREIGN KEY (center_attraction_key) REFERENCES dim_attraction(attraction_key),
    CONSTRAINT fk_edge_related FOREIGN KEY (related_attraction_key) REFERENCES dim_attraction(attraction_key),
    CONSTRAINT fk_edge_source FOREIGN KEY (source_id) REFERENCES data_source(source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fact_attraction_popularity (
    popularity_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    attraction_key VARCHAR(64) NOT NULL,
    dataset_type VARCHAR(30) NOT NULL,
    snapshot_year CHAR(4) NOT NULL,
    `year_month` CHAR(7) NULL,
    age_group VARCHAR(20) NOT NULL,
    rank_no SMALLINT UNSIGNED NULL,
    metric_value DECIMAL(14,4) NULL,
    value_unit VARCHAR(30) NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    CONSTRAINT fk_popularity_attraction FOREIGN KEY (attraction_key) REFERENCES dim_attraction(attraction_key),
    CONSTRAINT fk_popularity_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    UNIQUE KEY uq_attraction_popularity (attraction_key, dataset_type, snapshot_year, `year_month`, age_group, source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 서로 다른 외래객 지표를 long format으로 보존해 새 지표가 추가돼도 schema 변경을 줄인다.
CREATE TABLE IF NOT EXISTS fact_foreign_tourism_metric (
    foreign_metric_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    snapshot_year CHAR(4) NOT NULL,
    `year_month` CHAR(7) NULL,
    metric_name VARCHAR(80) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    dimension_name VARCHAR(50) NULL,
    dimension_value VARCHAR(150) NULL,
    metric_value DECIMAL(22,4) NOT NULL,
    unit VARCHAR(30) NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    CONSTRAINT fk_foreign_metric_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    KEY ix_foreign_metric_month (metric_name, `year_month`),
    KEY ix_foreign_dimension (dimension_name, dimension_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 전국·지역 현황 CSV의 다양한 수치 컬럼을 공통 long format으로 저장한다.
-- 원본에 단위가 없는 값은 unit='source_defined_unknown'으로 두고 정책 계산에 쓰지 않는다.
CREATE TABLE IF NOT EXISTS fact_tourism_benchmark_metric (
    benchmark_metric_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    dataset_name VARCHAR(150) NOT NULL,
    snapshot_year CHAR(4) NOT NULL,
    `year_month` CHAR(7) NULL,
    province_name VARCHAR(50) NULL,
    municipality_name VARCHAR(80) NULL,
    attraction_name VARCHAR(250) NULL,
    age_group VARCHAR(30) NULL,
    category_large VARCHAR(100) NULL,
    category_middle VARCHAR(100) NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(24,6) NOT NULL,
    unit VARCHAR(40) NOT NULL,
    dimensions_json JSON NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    source_row_number INT UNSIGNED NOT NULL,
    CONSTRAINT fk_benchmark_metric_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    KEY ix_benchmark_metric_period (dataset_name, metric_name, `year_month`),
    KEY ix_benchmark_metric_region (province_name, municipality_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 내용이 같은 파일의 canonical/alias 관계를 보존해 중복 적재 없이 원본 경로를 추적한다.
CREATE TABLE IF NOT EXISTS data_source_alias (
    alias_source_id VARCHAR(80) PRIMARY KEY,
    canonical_source_id VARCHAR(80) NOT NULL,
    alias_file_name VARCHAR(500) NOT NULL,
    file_hash CHAR(64) NOT NULL,
    CONSTRAINT fk_source_alias_canonical FOREIGN KEY (canonical_source_id) REFERENCES data_source(source_id),
    KEY ix_source_alias_hash (file_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 바깥 일괄다운로드 ZIP과 실제 Data Lab ZIP 사이의 부모-자식 출처 관계다.
CREATE TABLE IF NOT EXISTS data_source_lineage (
    parent_source_id VARCHAR(80) NOT NULL,
    child_source_id VARCHAR(80) NOT NULL,
    relation_type VARCHAR(30) NOT NULL,
    PRIMARY KEY (parent_source_id, child_source_id),
    CONSTRAINT fk_lineage_parent FOREIGN KEY (parent_source_id) REFERENCES data_source(source_id),
    CONSTRAINT fk_lineage_child FOREIGN KEY (child_source_id) REFERENCES data_source(source_id),
    CHECK (relation_type IN ('contains', 'derived_from'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

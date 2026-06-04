USE pm_travel;

CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    metric_name VARCHAR(100),
    value FLOAT,
    period VARCHAR(20),
    created_at DATETIME DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compliance_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    prospect_id INT,
    check_type VARCHAR(50),
    result VARCHAR(20),
    checked_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (prospect_id) REFERENCES prospects(id)
);

CREATE TABLE IF NOT EXISTS ab_tests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    campagne_id INT,
    variant_a_sujet TEXT,
    variant_b_sujet TEXT,
    opens_a INT DEFAULT 0,
    opens_b INT DEFAULT 0,
    winner VARCHAR(1),
    FOREIGN KEY (campagne_id) REFERENCES campagnes(id)
);

CREATE TABLE IF NOT EXISTS chatbot_conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100),
    platform VARCHAR(50),
    messages JSON,
    lead_detected BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(50),
    email VARCHAR(200),
    campagne_id INT,
    payload JSON,
    received_at DATETIME DEFAULT NOW()
);
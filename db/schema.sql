-- Master figure metadata sourced from MFC. Minimal MVP schema.
-- scale/classification are used only as crawl-time filters and not stored.
CREATE TABLE IF NOT EXISTS figures (
    id              INTEGER PRIMARY KEY,            -- MFC item id
    name_en         TEXT,
    maker           TEXT,                           -- "as Manufacturer/Circle" suffix stripped
    character_name  TEXT,
    origin          TEXT,                           -- 작품명
    release_date    TEXT,                           -- "MM/YYYY" as parsed from MFC
    msrp_jpy        INTEGER,                        -- nullable
    raw_meta_json   TEXT,                           -- full parsed payload for debugging
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_figures_maker  ON figures(maker);
CREATE INDEX IF NOT EXISTS idx_figures_char   ON figures(character_name);

-- Reference photos. Multiple rows per figure are allowed — the original
-- crawl drops a single canonical MFC product shot, and users can append
-- additional confirmed photos via /confirm_image to improve recall.
CREATE TABLE IF NOT EXISTS figure_images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    figure_id   INTEGER NOT NULL,
    image_path  TEXT NOT NULL,                      -- local filesystem path
    image_url   TEXT,                               -- original source URL
    source      TEXT DEFAULT 'mfc',                 -- 'mfc' | 'user_confirm' | 'manual'
    FOREIGN KEY (figure_id) REFERENCES figures(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_figure_images_figure ON figure_images(figure_id);

-- Partner store asking prices scraped from MFC item pages.
-- Multiple stores can carry the same figure; each row = one (figure, store, ts).
-- These are *current* asking prices, not sold prices.
CREATE TABLE IF NOT EXISTS partner_prices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    figure_id    INTEGER NOT NULL,
    store        TEXT NOT NULL,
    price        REAL NOT NULL,
    currency     TEXT NOT NULL,                     -- 'JPY' | 'USD' | 'EUR' | ...
    observed_at  TIMESTAMP NOT NULL,
    FOREIGN KEY (figure_id) REFERENCES figures(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_partner_figure ON partner_prices(figure_id);

-- Daily FX rate cache
CREATE TABLE IF NOT EXISTS fx_rates (
    date         TEXT PRIMARY KEY,                  -- YYYY-MM-DD
    jpy_to_krw   REAL NOT NULL,
    jpy_to_usd   REAL,
    fetched_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

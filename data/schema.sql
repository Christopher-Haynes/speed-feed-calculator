-- Material, machine and cutting data schema.
--
-- The CSV files in this folder are the source of truth. The app builds a
-- SQLite database from them every time it starts; the database itself is
-- not committed.
--
-- Data entry rules:
-- - Speeds and feeds are stored in inch units only (SFM, inches per
--   tooth, inches per rev). The app converts to metric.
-- - Every row needs source, source_ref, date_checked and confidence.
-- - date_checked is YYYY-MM-DD.
-- - Wrap any value that contains a comma in double quotes.
-- - Store only the values needed, with citations. Don't copy whole
--   Handbook tables into the repo.
-- - Never fill in a number the source doesn't give. Leave it blank.
--
-- Run `flask --app app check-data` after editing to check every row.


-- What the material is. One row per alloy and condition, so
-- 4140 annealed and 4140 hardened are separate rows. Leave condition
-- blank if the source doesn't give one.
CREATE TABLE materials (
    material_key   TEXT PRIMARY KEY,  -- short unique id, e.g. "4140-annealed"
    name           TEXT NOT NULL,     -- e.g. "4140"
    condition      TEXT,              -- e.g. "Annealed", "T6"
    iso_group      TEXT NOT NULL CHECK (iso_group IN ('P', 'M', 'K', 'N', 'S', 'H')),
    hardness_min   REAL,
    hardness_max   REAL,
    hardness_scale TEXT CHECK (hardness_scale IN ('HB', 'HRC')),
    notes          TEXT,
    source         TEXT NOT NULL,     -- book or site name, with edition
    source_ref     TEXT NOT NULL,     -- page/table or URL
    date_checked   TEXT NOT NULL,     -- YYYY-MM-DD
    confidence     TEXT NOT NULL CHECK (confidence IN ('handbook', 'manufacturer', 'shop-verified')),
    UNIQUE (name, condition)
);


-- Machine presets. Specs from official manufacturer spec sheets only.
CREATE TABLE machines (
    machine_key  TEXT PRIMARY KEY,   -- short unique id, e.g. "haas-vf2"
    name         TEXT NOT NULL,      -- e.g. "Haas VF-2"
    machine_type TEXT NOT NULL CHECK (machine_type IN ('mill', 'lathe')),
    max_rpm      REAL NOT NULL CHECK (max_rpm > 0),
    spindle_hp   REAL CHECK (spindle_hp IS NULL OR spindle_hp > 0),
    max_feed_ipm REAL CHECK (max_feed_ipm IS NULL OR max_feed_ipm > 0),
    taper        TEXT,               -- e.g. "CAT40", "BT30", "HSK63"
    notes        TEXT,
    source       TEXT NOT NULL,
    source_ref   TEXT NOT NULL,
    date_checked TEXT NOT NULL,
    confidence   TEXT NOT NULL CHECK (confidence IN ('handbook', 'manufacturer', 'shop-verified'))
);


-- Which tool a speed or feed row applies to (tool_type column below).
-- Values the app matches:
--   milling:  "flat", "ball", "bull nose", "chamfer", "face mill", or
--             "end mill" for any flat, ball or bull nose end mill
--   drilling: "drill"
-- Leave it blank if the row applies to any tool for that operation. The
-- most specific match wins: exact type, then "end mill", then blank.
--
-- Low / rec / high: give whatever the source gives. If it only gives a
-- range, leave rec blank and the app uses the middle of the range (and
-- says so). If it only gives one number, put it in rec.


-- Surface speed for a material, by operation and tool.
-- More than one source per combination is allowed, for cross-checking.
-- The app uses shop-verified first, then manufacturer, then handbook.
CREATE TABLE cutting_speeds (
    material_key  TEXT NOT NULL REFERENCES materials (material_key),
    operation     TEXT NOT NULL CHECK (operation IN ('milling', 'drilling', 'turning')),
    tool_material TEXT NOT NULL CHECK (tool_material IN ('HSS', 'cobalt', 'carbide')),
    tool_type     TEXT,
    sfm_low       REAL CHECK (sfm_low IS NULL OR sfm_low > 0),
    sfm_rec       REAL CHECK (sfm_rec IS NULL OR sfm_rec > 0),
    sfm_high      REAL CHECK (sfm_high IS NULL OR sfm_high > 0),
    notes         TEXT,
    source        TEXT NOT NULL,
    source_ref    TEXT NOT NULL,
    date_checked  TEXT NOT NULL,
    confidence    TEXT NOT NULL CHECK (confidence IN ('handbook', 'manufacturer', 'shop-verified')),
    CHECK (sfm_rec IS NOT NULL OR (sfm_low IS NOT NULL AND sfm_high IS NOT NULL)),
    CHECK (sfm_low IS NULL OR sfm_high IS NULL OR sfm_low <= sfm_high),
    CHECK (sfm_rec IS NULL OR sfm_low IS NULL OR sfm_low <= sfm_rec),
    CHECK (sfm_rec IS NULL OR sfm_high IS NULL OR sfm_rec <= sfm_high),
    UNIQUE (material_key, operation, tool_material, tool_type, source)
);


-- Feed for a material, by operation and tool.
-- Milling feeds are inches per tooth (chip load).
-- Drilling and turning feeds are inches per rev.
-- Diameter range: leave blank if the feed doesn't depend on tool size.
-- When a tool fits more than one range, the range starting closest
-- below the tool's diameter wins, so a source that lists chip load at
-- set sizes can be entered as "this size up to the next size".
CREATE TABLE feeds (
    material_key    TEXT NOT NULL REFERENCES materials (material_key),
    operation       TEXT NOT NULL CHECK (operation IN ('milling', 'drilling', 'turning')),
    tool_material   TEXT NOT NULL CHECK (tool_material IN ('HSS', 'cobalt', 'carbide')),
    tool_type       TEXT,
    diameter_min_in REAL CHECK (diameter_min_in IS NULL OR diameter_min_in >= 0),
    diameter_max_in REAL CHECK (diameter_max_in IS NULL OR diameter_min_in IS NULL
                                OR diameter_max_in >= diameter_min_in),
    feed_low        REAL CHECK (feed_low IS NULL OR feed_low > 0),
    feed_rec        REAL CHECK (feed_rec IS NULL OR feed_rec > 0),
    feed_high       REAL CHECK (feed_high IS NULL OR feed_high > 0),
    notes           TEXT,
    source          TEXT NOT NULL,
    source_ref      TEXT NOT NULL,
    date_checked    TEXT NOT NULL,
    confidence      TEXT NOT NULL CHECK (confidence IN ('handbook', 'manufacturer', 'shop-verified')),
    CHECK (feed_rec IS NOT NULL OR (feed_low IS NOT NULL AND feed_high IS NOT NULL)),
    CHECK (feed_low IS NULL OR feed_high IS NULL OR feed_low <= feed_high),
    CHECK (feed_rec IS NULL OR feed_low IS NULL OR feed_low <= feed_rec),
    CHECK (feed_rec IS NULL OR feed_high IS NULL OR feed_rec <= feed_high)
);


-- Unit power: horsepower needed to remove one cubic inch per minute of
-- the material. Used for the spindle horsepower check.
CREATE TABLE unit_power (
    material_key   TEXT NOT NULL REFERENCES materials (material_key),
    hp_per_in3_min REAL NOT NULL CHECK (hp_per_in3_min > 0),
    notes          TEXT,
    source         TEXT NOT NULL,
    source_ref     TEXT NOT NULL,
    date_checked   TEXT NOT NULL,
    confidence     TEXT NOT NULL CHECK (confidence IN ('handbook', 'manufacturer', 'shop-verified')),
    UNIQUE (material_key, source)
);

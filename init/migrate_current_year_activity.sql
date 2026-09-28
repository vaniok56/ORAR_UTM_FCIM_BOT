USE orar_bot;

INSERT INTO app_settings (setting_name, setting_value)
VALUES ('current_year', '27')
ON DUPLICATE KEY UPDATE setting_value = setting_value;

UPDATE settings
SET last_cmd = NULL
WHERE last_cmd = 'none' OR last_cmd = '';

ALTER TABLE settings
CHANGE COLUMN last_cmd last_interaction_at DATETIME NULL DEFAULT NULL;

CREATE INDEX idx_settings_last_interaction_at
ON settings (last_interaction_at);

DROP PROCEDURE IF EXISTS migrate;
DROP PROCEDURE IF EXISTS get_all_users;
DROP PROCEDURE IF EXISTS get_all_users_with;
DROP PROCEDURE IF EXISTS get_all_users_without;
DROP PROCEDURE IF EXISTS select_all_user_data;

DELIMITER //
CREATE PROCEDURE migrate(
    IN sender VARCHAR(15),
    IN group_n VARCHAR(10),
    IN spec VARCHAR(5),
    IN year_s SMALLINT,
    IN subgrupa SMALLINT,
    IN noti VARCHAR(5),
    IN admins SMALLINT,
    IN prem SMALLINT,
    IN gamble INT,
    IN ban SMALLINT,
    IN ban_time VARCHAR(50),
    IN last_interaction_at DATETIME,
    IN lang VARCHAR(5)
)
BEGIN
    DECLARE noti_value SMALLINT;

    SET group_n = IF(group_n = '' OR group_n IS NULL, 'none', group_n);
    SET spec = IF(spec = '' OR spec IS NULL, 'none', spec);
    SET year_s = IF(year_s = '' OR year_s IS NULL, 0, year_s);
    SET subgrupa = IF(subgrupa = '' OR subgrupa IS NULL, 0, subgrupa);
    SET noti_value = IF(noti = 'on', 1, 0);
    SET admins = IF(admins = '' OR admins IS NULL, 0, admins);
    SET prem = IF(prem = '' OR prem IS NULL, 0, prem);
    SET gamble = IF(gamble = '' OR gamble IS NULL, 0, gamble);
    SET ban = IF(ban = '' OR ban IS NULL, 0, ban);
    SET ban_time = IF(ban_time = '' OR ban_time IS NULL, 'none', ban_time);
    SET lang = IF(lang = '' OR lang IS NULL, 'none', lang);

    INSERT INTO users (SENDER, group_n, spec, year_s, subgrupa)
    VALUES (sender, group_n, spec, year_s, subgrupa)
    ON DUPLICATE KEY UPDATE
        group_n = VALUES(group_n),
        spec = VALUES(spec),
        year_s = VALUES(year_s),
        subgrupa = VALUES(subgrupa),
        id = LAST_INSERT_ID(id);

    SET @user_id = LAST_INSERT_ID();

    INSERT INTO settings (id, noti, admins, prem, gamble, ban, ban_time, last_interaction_at, lang)
    VALUES (@user_id, noti_value, admins, prem, gamble, ban, ban_time, last_interaction_at, lang)
    ON DUPLICATE KEY UPDATE
        noti = VALUES(noti),
        admins = VALUES(admins),
        prem = VALUES(prem),
        gamble = VALUES(gamble),
        ban = VALUES(ban),
        ban_time = VALUES(ban_time),
        last_interaction_at = VALUES(last_interaction_at),
        lang = VALUES(lang);
END //

CREATE PROCEDURE get_all_users()
BEGIN
    SELECT u.SENDER, u.group_n, u.spec, u.year_s, u.subgrupa,
           s.noti, s.admins, s.prem, s.gamble, s.ban, s.ban_time, s.last_interaction_at, s.lang
    FROM users u
    JOIN settings s ON u.id = s.id;
END //

CREATE PROCEDURE get_all_users_with(
    IN field VARCHAR(50),
    IN field_value VARCHAR(50)
)
BEGIN
    SET @field_val = field;
    SET @value_val = field_value;
    SET @query = CONCAT('SELECT u.SENDER, u.group_n, u.spec, u.year_s, u.subgrupa, ',
                        's.noti, s.admins, s.prem, s.gamble, s.ban, s.ban_time, s.last_interaction_at, s.lang ',
                        'FROM users u JOIN settings s ON u.id = s.id WHERE ', @field_val, ' = ?');
    PREPARE stmt FROM @query;
    EXECUTE stmt USING @value_val;
    DEALLOCATE PREPARE stmt;
END //

CREATE PROCEDURE get_all_users_without(
    IN field VARCHAR(50),
    IN field_value VARCHAR(50)
)
BEGIN
    SET @field_val = field;
    SET @value_val = field_value;
    SET @query = CONCAT('SELECT u.SENDER, u.group_n, u.spec, u.year_s, u.subgrupa, ',
                        's.noti, s.admins, s.prem, s.gamble, s.ban, s.ban_time, s.last_interaction_at, s.lang ',
                        'FROM users u JOIN settings s ON u.id = s.id WHERE ', @field_val, ' != ?');
    PREPARE stmt FROM @query;
    EXECUTE stmt USING @value_val;
    DEALLOCATE PREPARE stmt;
END //

CREATE PROCEDURE select_all_user_data(
    IN sender VARCHAR(15)
)
BEGIN
    SELECT u.SENDER, u.group_n, u.spec, u.year_s, u.subgrupa,
           s.noti, s.admins, s.prem, s.gamble, s.ban, s.ban_time, s.last_interaction_at, s.lang
    FROM users u
    JOIN settings s ON u.id = s.id
    WHERE u.SENDER = sender COLLATE utf8mb4_unicode_ci;
END //
DELIMITER ;

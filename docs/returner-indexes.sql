-- Indexes Alcali wants on an existing Salt returner database.
--
-- Salt's own DDL for salt.returners.mysql indexes salt_returns by id, jid and
-- fun, and salt_events by tag. Alcali orders by alter_time on nearly every
-- query, so on a database that has been collecting returns for a while those
-- queries degrade into a full scan plus a filesort over two mediumtext
-- columns. `manage.py diagnose` reports which of these are missing.
--
-- Adding an index to a large InnoDB table is online in MySQL 5.6+/MariaDB 10.0+
-- but still costs I/O; run it during a quiet period.

ALTER TABLE `salt_returns` ADD INDEX `alter_time` (`alter_time`);
ALTER TABLE `salt_returns` ADD INDEX `id_alter_time` (`id`, `alter_time`);
ALTER TABLE `salt_events` ADD INDEX `alter_time` (`alter_time`);

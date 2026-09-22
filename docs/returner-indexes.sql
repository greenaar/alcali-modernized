-- Indexes Alcali wants on an existing Salt returner database.
--
-- `alcali migrate` adds these itself (migration 0010), and
-- `alcali returner_indexes --apply` adds any that are missing later. This file
-- is for when the database user Alcali runs as may not alter Salt's tables.
--
-- Salt's own DDL for salt.returners.mysql indexes salt_returns by id, jid and
-- fun, and salt_events by tag. Alcali orders by alter_time on nearly every
-- query and looks up each minion's state runs by (id, fun), so on a database
-- that has been collecting returns for a while those queries degrade into a
-- full scan plus a filesort over two mediumtext columns.
-- `alcali diagnose` reports which of these are missing, matched on leading
-- columns, so an equivalent index under another name also counts.
--
-- ALGORITHM=INPLACE, LOCK=NONE keeps the master's returner writing while the
-- index builds (MySQL 5.6+/MariaDB 10.0+); it still costs I/O, so run it
-- during a quiet period.

ALTER TABLE `salt_returns` ADD INDEX `alcali_ret_alter_time` (`alter_time`), ALGORITHM=INPLACE, LOCK=NONE;
ALTER TABLE `salt_returns` ADD INDEX `alcali_ret_id_alter_time` (`id`, `alter_time`), ALGORITHM=INPLACE, LOCK=NONE;
ALTER TABLE `salt_returns` ADD INDEX `alcali_ret_id_fun_jid` (`id`, `fun`, `jid`), ALGORITHM=INPLACE, LOCK=NONE;
ALTER TABLE `salt_events` ADD INDEX `alcali_evt_alter_time` (`alter_time`), ALGORITHM=INPLACE, LOCK=NONE;

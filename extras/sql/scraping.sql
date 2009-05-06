DROP TABLE IF EXISTS `url_history`;
DROP TABLE IF EXISTS `version`;
DROP TABLE IF EXISTS `url_status`;
DROP TABLE IF EXISTS `ticket`;
DROP TABLE IF EXISTS `domain_stats`;
DROP TABLE IF EXISTS `domain_stats_history`;
DROP TABLE IF EXISTS `domain_data_history`;

CREATE TABLE `ticket` (
  `guid` char(40) NOT NULL,
  `domain` varchar(255) default NULL,
  `url` varchar(2048) default NULL,
  `url_hash` char(40) default NULL, -- so we can join to url_status
  PRIMARY KEY  (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `version` (
  `id` bigint(20) NOT NULL auto_increment,
  `guid` char(40) NOT NULL,
  `version` char(40) NOT NULL,
  `seen` datetime NOT NULL,
  PRIMARY KEY  (`id`),
  FOREIGN KEY (`guid`) REFERENCES ticket(guid) ON UPDATE CASCADE ON DELETE CASCADE,
  UNIQUE KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `url_status` (
  -- see http://support.microsoft.com/kb/q208427/ for explanation of 2048
  `url_hash` char(40) NOT NULL,         -- for faster searches
  `url` varchar(2048) NOT NULL,
  `parent_hash` char(40) default NULL,  -- the url that was followed to this one - for reporting
  `last_version` char(40) default NULL, -- can be null if it generated an error the last time is was checked
  `last_checked`  datetime NOT NULL,
  PRIMARY KEY  (`url_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `url_history` (
   `url_hash` char(40) NOT NULL,
   `version` char(40) NOT NULL,
   `postdata_hash` char(40) default NULL,
   `created` datetime NOT NULL,
   PRIMARY KEY (`version`),
   FOREIGN KEY (`url_hash`) REFERENCES url_status(url_hash) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `domain_stats` (
  `key1` varchar(128) NOT NULL,
  `key2` varchar(128) NOT NULL,
  `value` text,
  PRIMARY KEY `key1_key2` (`key1`, `key2`),
  KEY `key1` (`key1`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `domain_stats_history` (
  `id` bigint(20) NOT NULL auto_increment,
  `key1` varchar(128) NOT NULL,
  `key2` varchar(128) NOT NULL,
  `value` varchar(2048) NOT NULL,
  `stored` datetime NOT NULL,
  PRIMARY KEY  (`id`),
  KEY `key1_key2` (`key1`, `key2`),
  KEY `key1` (`key1`),
  KEY `stored` (`stored`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `domain_data_history` (
  `domain` varchar(255) NOT NULL,
  `stored` datetime NOT NULL,
  `data` text,
  KEY `domain_stored` (`domain`, `stored`),
  KEY `domain` (`domain`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

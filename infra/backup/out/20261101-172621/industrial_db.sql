-- MySQL dump 10.13  Distrib 8.4.11, for Linux (x86_64)
--
-- Host: localhost    Database: industrial_db
-- ------------------------------------------------------
-- Server version	8.4.11

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
INSERT INTO `alembic_version` VALUES ('0005_idempotency');
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `customer`
--

DROP TABLE IF EXISTS `customer`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `customer` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `customer_code` varchar(32) NOT NULL,
  `customer_name` varchar(150) NOT NULL,
  `contact_name` varchar(60) NOT NULL,
  `contact_phone` varchar(30) DEFAULT NULL,
  `contact_email` varchar(120) DEFAULT NULL,
  `service_level` varchar(20) NOT NULL,
  `status` varchar(20) NOT NULL,
  `address` varchar(255) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_customer_customer_code` (`customer_code`),
  CONSTRAINT `ck_customer_ck_customer_service_level` CHECK ((`service_level` in (_utf8mb4'STANDARD',_utf8mb4'PRIORITY'))),
  CONSTRAINT `ck_customer_ck_customer_status` CHECK ((`status` in (_utf8mb4'ACTIVE',_utf8mb4'INACTIVE')))
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `customer`
--

LOCK TABLES `customer` WRITE;
/*!40000 ALTER TABLE `customer` DISABLE KEYS */;
INSERT INTO `customer` VALUES (1,'CUST-SYN-001','合成制造一厂','王工','13800000001','wang@example.com','PRIORITY','ACTIVE','合成市工业区 1 号','2026-11-01 04:46:15.402421','2026-11-01 04:46:15.402426'),(2,'CUST-SYN-002','合成能源二厂','李工','13800000002','li@example.com','STANDARD','ACTIVE','合成市能源路 8 号','2026-11-01 04:46:15.405248','2026-11-01 04:46:15.405253');
/*!40000 ALTER TABLE `customer` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `device`
--

DROP TABLE IF EXISTS `device`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `device` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_code` varchar(40) NOT NULL,
  `serial_number` varchar(80) NOT NULL,
  `model_id` bigint NOT NULL,
  `customer_id` bigint NOT NULL,
  `installation_date` date DEFAULT NULL,
  `warranty_start_date` date DEFAULT NULL,
  `warranty_end_date` date DEFAULT NULL,
  `location` varchar(255) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_device_device_code` (`device_code`),
  UNIQUE KEY `uq_device_serial_number` (`serial_number`),
  KEY `fk_device_model_id_product_model` (`model_id`),
  KEY `ix_device_customer_status` (`customer_id`,`status`),
  CONSTRAINT `fk_device_customer_id_customer` FOREIGN KEY (`customer_id`) REFERENCES `customer` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_device_model_id_product_model` FOREIGN KEY (`model_id`) REFERENCES `product_model` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_device_ck_device_status` CHECK ((`status` in (_utf8mb4'ACTIVE',_utf8mb4'MAINTENANCE',_utf8mb4'RETIRED'))),
  CONSTRAINT `ck_device_ck_device_warranty_range` CHECK ((((`warranty_start_date` is null) and (`warranty_end_date` is null)) or ((`warranty_start_date` is not null) and (`warranty_end_date` is not null) and (`warranty_end_date` >= `warranty_start_date`))))
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `device`
--

LOCK TABLES `device` WRITE;
/*!40000 ALTER TABLE `device` DISABLE KEYS */;
INSERT INTO `device` VALUES (1,'DEV-SYN-0001','SN-HC200-0001',1,1,'2025-03-01','2025-03-01','2027-03-01','一号车间','ACTIVE','2026-11-01 04:46:15.414415','2026-11-01 04:46:15.414419'),(2,'DEV-SYN-0002','SN-HC200-0002',1,1,'2025-06-01','2025-06-01','2027-06-01','二号车间','ACTIVE','2026-11-01 04:46:15.417063','2026-11-01 04:46:15.417067'),(3,'DEV-SYN-0003','SN-SC100-0001',2,2,'2024-01-15','2024-01-15','2025-01-15','能源站','ACTIVE','2026-11-01 04:46:15.418725','2026-11-01 04:46:15.418729');
/*!40000 ALTER TABLE `device` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `duplicate_confirmation`
--

DROP TABLE IF EXISTS `duplicate_confirmation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `duplicate_confirmation` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `token_hash` varchar(64) NOT NULL,
  `caller_scope` varchar(100) NOT NULL,
  `params_digest` varchar(64) NOT NULL,
  `candidate_set_digest` varchar(64) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `consumed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_duplicate_confirmation_token_hash` (`token_hash`),
  KEY `ix_duplicate_confirmation_hash` (`token_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `duplicate_confirmation`
--

LOCK TABLES `duplicate_confirmation` WRITE;
/*!40000 ALTER TABLE `duplicate_confirmation` DISABLE KEYS */;
/*!40000 ALTER TABLE `duplicate_confirmation` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `fault_record`
--

DROP TABLE IF EXISTS `fault_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `fault_record` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `fault_no` varchar(40) NOT NULL,
  `device_id` bigint NOT NULL,
  `fault_code` varchar(40) DEFAULT NULL,
  `title` varchar(150) NOT NULL,
  `description` text NOT NULL,
  `severity` varchar(20) NOT NULL,
  `occurred_at` datetime(6) NOT NULL,
  `reported_by_ref` varchar(100) DEFAULT NULL,
  `source` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_fault_record_fault_no` (`fault_no`),
  KEY `ix_fault_record_device_occurred` (`device_id`,`occurred_at`),
  CONSTRAINT `fk_fault_record_device_id_device` FOREIGN KEY (`device_id`) REFERENCES `device` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_fault_record_ck_fault_record_severity` CHECK ((`severity` in (_utf8mb4'LOW',_utf8mb4'MEDIUM',_utf8mb4'HIGH',_utf8mb4'CRITICAL'))),
  CONSTRAINT `ck_fault_record_ck_fault_record_source` CHECK ((`source` in (_utf8mb4'MANUAL',_utf8mb4'AGENT',_utf8mb4'SYSTEM')))
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `fault_record`
--

LOCK TABLES `fault_record` WRITE;
/*!40000 ALTER TABLE `fault_record` DISABLE KEYS */;
INSERT INTO `fault_record` VALUES (1,'FAULT-SYN-0001',1,'E03','工业网关通信异常','HC200-0001 间歇断连，重启后恢复','HIGH','2026-10-20 08:30:00.000000','flowai-user-customer-001','MANUAL','2026-11-01 04:46:15.439847'),(2,'FAULT-SYN-0002',2,'E07','采集延迟超阈值','数据上报延迟超过 30 秒','MEDIUM','2026-10-25 14:00:00.000000','flowai-user-customer-001','AGENT','2026-11-01 04:46:15.441897'),(3,'FAULT-SYN-0003',3,'E11','通道 3 无数据','采集器通道 3 持续无读数','CRITICAL','2026-10-26 09:15:00.000000',NULL,'SYSTEM','2026-11-01 04:46:15.444123');
/*!40000 ALTER TABLE `fault_record` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `idempotency_record`
--

DROP TABLE IF EXISTS `idempotency_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `idempotency_record` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `operation` varchar(40) NOT NULL,
  `caller_scope` varchar(100) NOT NULL,
  `idempotency_key` varchar(120) NOT NULL,
  `request_hash` varchar(64) NOT NULL,
  `status` varchar(20) NOT NULL,
  `response_status` int DEFAULT NULL,
  `response_body` json DEFAULT NULL,
  `resource_type` varchar(40) DEFAULT NULL,
  `resource_id` bigint DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_idempotency_scope_operation_key` (`caller_scope`,`operation`,`idempotency_key`),
  KEY `ix_idempotency_expires_at` (`expires_at`),
  CONSTRAINT `ck_idempotency_record_ck_idempotency_record_status` CHECK ((`status` in (_utf8mb4'PROCESSING',_utf8mb4'SUCCEEDED',_utf8mb4'FAILED')))
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `idempotency_record`
--

LOCK TABLES `idempotency_record` WRITE;
/*!40000 ALTER TABLE `idempotency_record` DISABLE KEYS */;
INSERT INTO `idempotency_record` VALUES (1,'create_ticket','admin','agent-1-6dc84995fd704794','177a26803ed763cd79b536445e01defc09e37372c3c28751ff1300ded13e7320','SUCCEEDED',201,'{\"code\": \"SUCCESS\", \"data\": {\"id\": 1, \"title\": \"DEV-SYN-0001 故障维修\", \"source\": \"MANUAL\", \"status\": \"PENDING\", \"version\": 1, \"fault_id\": null, \"priority\": \"NORMAL\", \"closed_at\": null, \"device_id\": 1, \"ticket_no\": \"WO-20261101-0001\", \"created_at\": \"2026-11-01T08:11:14.925443\", \"resolution\": null, \"updated_at\": \"2026-11-01T08:11:14.925450\", \"assignee_id\": null, \"customer_id\": 1, \"description\": \"device_id: 1 HC200 通信异常，请帮我创建工单\", \"resolved_at\": null, \"requester_ref\": \"admin\", \"reported_fault_code\": null}, \"message\": \"维修工单创建成功\", \"trace_id\": \"c9b893a8affb4df1a8b3625e9664ff37\"}','repair_ticket',1,'2026-11-01 08:11:14.914597','2026-11-02 08:11:14.912264');
/*!40000 ALTER TABLE `idempotency_record` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `product_model`
--

DROP TABLE IF EXISTS `product_model`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `product_model` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `model_code` varchar(40) NOT NULL,
  `model_name` varchar(120) NOT NULL,
  `category` varchar(60) NOT NULL,
  `manufacturer` varchar(120) NOT NULL,
  `specification` json DEFAULT NULL,
  `warranty_months` smallint NOT NULL,
  `status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_product_model_model_code` (`model_code`),
  CONSTRAINT `ck_product_model_ck_product_model_status` CHECK ((`status` in (_utf8mb4'ACTIVE',_utf8mb4'DISCONTINUED'))),
  CONSTRAINT `ck_product_model_ck_product_model_warranty_months` CHECK (((`warranty_months` >= 0) and (`warranty_months` <= 120)))
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `product_model`
--

LOCK TABLES `product_model` WRITE;
/*!40000 ALTER TABLE `product_model` DISABLE KEYS */;
INSERT INTO `product_model` VALUES (1,'HC200','工业网关 HC200','gateway','合成工业设备','{\"ports\": 4, \"protocol\": [\"Modbus\", \"MQTT\"]}',24,'ACTIVE','2026-11-01 04:46:15.408639','2026-11-01 04:46:15.408643'),(2,'SC100','数据采集器 SC100','sensor','合成工业设备','{\"channels\": 8}',12,'ACTIVE','2026-11-01 04:46:15.410983','2026-11-01 04:46:15.410986');
/*!40000 ALTER TABLE `product_model` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `repair_ticket`
--

DROP TABLE IF EXISTS `repair_ticket`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `repair_ticket` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ticket_no` varchar(40) NOT NULL,
  `customer_id` bigint NOT NULL,
  `device_id` bigint NOT NULL,
  `fault_id` bigint DEFAULT NULL,
  `title` varchar(150) NOT NULL,
  `description` text NOT NULL,
  `reported_fault_code` varchar(40) DEFAULT NULL,
  `priority` varchar(20) NOT NULL,
  `status` varchar(20) NOT NULL,
  `assignee_id` bigint DEFAULT NULL,
  `source` varchar(20) NOT NULL,
  `requester_ref` varchar(100) NOT NULL,
  `resolution` text,
  `version` int NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `resolved_at` datetime(6) DEFAULT NULL,
  `closed_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_repair_ticket_ticket_no` (`ticket_no`),
  KEY `fk_repair_ticket_fault_id_fault_record` (`fault_id`),
  KEY `ix_ticket_customer_status_created` (`customer_id`,`status`,`created_at`),
  KEY `ix_ticket_device_status_created` (`device_id`,`status`,`created_at`),
  KEY `ix_ticket_assignee_status` (`assignee_id`,`status`),
  CONSTRAINT `fk_repair_ticket_assignee_id_service_user` FOREIGN KEY (`assignee_id`) REFERENCES `service_user` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_repair_ticket_customer_id_customer` FOREIGN KEY (`customer_id`) REFERENCES `customer` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_repair_ticket_device_id_device` FOREIGN KEY (`device_id`) REFERENCES `device` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_repair_ticket_fault_id_fault_record` FOREIGN KEY (`fault_id`) REFERENCES `fault_record` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_repair_ticket_ck_repair_ticket_priority` CHECK ((`priority` in (_utf8mb4'LOW',_utf8mb4'NORMAL',_utf8mb4'HIGH',_utf8mb4'URGENT'))),
  CONSTRAINT `ck_repair_ticket_ck_repair_ticket_source` CHECK ((`source` in (_utf8mb4'MANUAL',_utf8mb4'AGENT',_utf8mb4'SYSTEM'))),
  CONSTRAINT `ck_repair_ticket_ck_repair_ticket_status` CHECK ((`status` in (_utf8mb4'PENDING',_utf8mb4'IN_PROGRESS',_utf8mb4'RESOLVED',_utf8mb4'CLOSED',_utf8mb4'REOPENED'))),
  CONSTRAINT `ck_repair_ticket_ck_repair_ticket_version` CHECK ((`version` >= 1))
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `repair_ticket`
--

LOCK TABLES `repair_ticket` WRITE;
/*!40000 ALTER TABLE `repair_ticket` DISABLE KEYS */;
INSERT INTO `repair_ticket` VALUES (1,'WO-20261101-0001',1,1,NULL,'DEV-SYN-0001 故障维修','device_id: 1 HC200 通信异常，请帮我创建工单',NULL,'NORMAL','PENDING',NULL,'MANUAL','admin',NULL,1,'2026-11-01 08:11:14.925443','2026-11-01 08:11:14.925450',NULL,NULL);
/*!40000 ALTER TABLE `repair_ticket` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `schema_meta`
--

DROP TABLE IF EXISTS `schema_meta`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `schema_meta` (
  `meta_key` varchar(64) NOT NULL,
  `meta_value` varchar(255) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`meta_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `schema_meta`
--

LOCK TABLES `schema_meta` WRITE;
/*!40000 ALTER TABLE `schema_meta` DISABLE KEYS */;
/*!40000 ALTER TABLE `schema_meta` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_identity_binding`
--

DROP TABLE IF EXISTS `service_identity_binding`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `service_identity_binding` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `identity_provider` varchar(40) NOT NULL,
  `external_user_id` varchar(100) NOT NULL,
  `service_user_id` bigint DEFAULT NULL,
  `customer_id` bigint DEFAULT NULL,
  `business_role` varchar(20) NOT NULL,
  `status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_binding_provider_external` (`identity_provider`,`external_user_id`),
  KEY `fk_binding_customer_id_customer` (`customer_id`),
  KEY `fk_binding_service_user_id_service_user` (`service_user_id`),
  KEY `ix_binding_external` (`identity_provider`,`external_user_id`),
  CONSTRAINT `fk_binding_customer_id_customer` FOREIGN KEY (`customer_id`) REFERENCES `customer` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_binding_service_user_id_service_user` FOREIGN KEY (`service_user_id`) REFERENCES `service_user` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_service_identity_binding_ck_binding_business_role` CHECK ((`business_role` in (_utf8mb4'CUSTOMER_USER',_utf8mb4'SERVICE_STAFF',_utf8mb4'SERVICE_ADMIN'))),
  CONSTRAINT `ck_service_identity_binding_ck_binding_role_consistency` CHECK ((((`business_role` = _utf8mb4'CUSTOMER_USER') and (`customer_id` is not null) and (`service_user_id` is null)) or ((`business_role` in (_utf8mb4'SERVICE_STAFF',_utf8mb4'SERVICE_ADMIN')) and (`service_user_id` is not null)))),
  CONSTRAINT `ck_service_identity_binding_ck_binding_status` CHECK ((`status` in (_utf8mb4'ACTIVE',_utf8mb4'REVOKED')))
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_identity_binding`
--

LOCK TABLES `service_identity_binding` WRITE;
/*!40000 ALTER TABLE `service_identity_binding` DISABLE KEYS */;
INSERT INTO `service_identity_binding` VALUES (1,'flowai','flowai-user-customer-001',NULL,1,'CUSTOMER_USER','ACTIVE','2026-11-01 04:46:15.427637'),(2,'flowai','flowai-user-customer-002',NULL,2,'CUSTOMER_USER','ACTIVE','2026-11-01 04:46:15.430030'),(3,'flowai','flowai-user-staff-001',1,NULL,'SERVICE_STAFF','ACTIVE','2026-11-01 04:46:15.433212'),(4,'flowai','flowai-user-admin-001',2,NULL,'SERVICE_ADMIN','ACTIVE','2026-11-01 04:46:15.435117'),(5,'flowai','admin',2,NULL,'SERVICE_ADMIN','ACTIVE','2026-11-01 08:08:57.139020');
/*!40000 ALTER TABLE `service_identity_binding` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_user`
--

DROP TABLE IF EXISTS `service_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `service_user` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_code` varchar(40) NOT NULL,
  `display_name` varchar(80) NOT NULL,
  `department` varchar(80) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_service_user_staff_code` (`staff_code`),
  CONSTRAINT `ck_service_user_ck_service_user_status` CHECK ((`status` in (_utf8mb4'ACTIVE',_utf8mb4'INACTIVE')))
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_user`
--

LOCK TABLES `service_user` WRITE;
/*!40000 ALTER TABLE `service_user` DISABLE KEYS */;
INSERT INTO `service_user` VALUES (1,'STAFF-SYN-001','张工','售后一部','ACTIVE','2026-11-01 04:46:15.422457','2026-11-01 04:46:15.422461'),(2,'STAFF-SYN-002','赵工','售后二部','ACTIVE','2026-11-01 04:46:15.424360','2026-11-01 04:46:15.424363');
/*!40000 ALTER TABLE `service_user` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `ticket_action`
--

DROP TABLE IF EXISTS `ticket_action`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_action` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ticket_id` bigint NOT NULL,
  `action_type` varchar(20) NOT NULL,
  `actor_type` varchar(20) NOT NULL,
  `actor_ref` varchar(100) NOT NULL,
  `initiated_by_ref` varchar(100) DEFAULT NULL,
  `old_status` varchar(20) DEFAULT NULL,
  `new_status` varchar(20) DEFAULT NULL,
  `details` json DEFAULT NULL,
  `comment` text,
  `trace_id` varchar(64) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_ticket_action_ticket_created` (`ticket_id`,`created_at`,`id`),
  CONSTRAINT `fk_ticket_action_ticket_id_repair_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `repair_ticket` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_ticket_action_ck_ticket_action_action_type` CHECK ((`action_type` in (_utf8mb4'CREATE',_utf8mb4'ASSIGN',_utf8mb4'STATUS_CHANGE',_utf8mb4'LINK_FAULT',_utf8mb4'COMMENT'))),
  CONSTRAINT `ck_ticket_action_ck_ticket_action_actor_type` CHECK ((`actor_type` in (_utf8mb4'USER',_utf8mb4'SERVICE_USER',_utf8mb4'SYSTEM',_utf8mb4'AGENT')))
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `ticket_action`
--

LOCK TABLES `ticket_action` WRITE;
/*!40000 ALTER TABLE `ticket_action` DISABLE KEYS */;
INSERT INTO `ticket_action` VALUES (1,1,'CREATE','SERVICE_USER','admin',NULL,NULL,'PENDING','{\"fault_id\": null, \"priority\": \"NORMAL\", \"device_id\": 1}',NULL,'c9b893a8affb4df1a8b3625e9664ff37','2026-11-01 08:11:14.929790');
/*!40000 ALTER TABLE `ticket_action` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'industrial_db'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-01  9:26:22

# Benchmark Dataset Specification & Data Engineering Protocol

This document outlines the benchmark datasets used to train, evaluate, and benchmark the **LogPulse AnomalyGuard** platform.

---

## 1. Datasets Overview & Provenance

| Property | HDFS Dataset | BGL Dataset |
| :--- | :--- | :--- |
| **Full Name** | Hadoop Distributed File System Logs | BlueGene/L Supercomputer Logs |
| **Originating System**| Hadoop cluster running on 203 EC2 nodes | BlueGene/L cluster at Lawrence Livermore National Lab (LLNL) |
| **Benchmark Provider**| **Loghub** (LogPAI research group) | **Loghub** (LogPAI research group) |
| **Reference Citation**| He, P. et al., *Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics*, ISSRE 2020 | Zhu, J. et al., *Tools and Benchmarks for Automated Log Parsing*, ICSE 2019 |
| **License** | Open Access for Research and Benchmarking (Loghub terms) | Open Access for Research and Benchmarking (LLNL / Loghub) |
| **Format** | Semi-structured application logs | System and hardware event logs |
| **Target Task** | Sequential block-level anomaly detection | Chronological event & alert anomaly detection |

---

## 2. Dataset Schemas & Record Specifications

### A. HDFS Dataset Schema
Sample raw log line:
```text
081109 203615 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_38865049064139660 terminating
```

| Field Name | Type | Description | Extraction Pattern |
| :--- | :--- | :--- | :--- |
| `date` | String | Date in YYMMDD format | `(?P<date>\d{6})` |
| `time` | String | Time in HHMMSS format | `(?P<time>\d{6})` |
| `timestamp` | ISO 8601 | Normalized UTC timestamp (`YYYY-MM-DDTHH:MM:SS+00:00`) | Extracted & formatted |
| `pid` | Integer | Process ID | `(?P<pid>\d+)` |
| `level` | String | Log severity (`INFO`, `WARN`, `ERROR`) | `(?P<level>\w+)` |
| `component` | String | Java class / subsystem (`dfs.DataNode`, `dfs.FSNamesystem`) | `(?P<component>[^:]+)` |
| `block_id` | String | Hadoop Data Block ID (`blk_-?[0-9]+`) | `(blk_-?\d+)` |
| `message` | String | Raw log message text | Remainder of string |
| `label` | String | Ground-truth classification: `Normal` or `Anomaly` | Looked up from `anomaly_label.csv` |

### B. BGL Dataset Schema
Sample raw log line:
```text
- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected
```

| Field Name | Type | Description | Extraction Pattern |
| :--- | :--- | :--- | :--- |
| `raw_label` | String | `-` for normal logs; Alert category (e.g., `APP`, `KERN`, `FATAL`) for anomalies | First token `(?P<label>\S+)` |
| `label` | String | Normalized label: `Normal` or `Anomaly` | Derived: `Anomaly` if `raw_label != '-'` else `Normal` |
| `epoch` | Integer | Unix epoch seconds | `(?P<epoch>\d+)` |
| `timestamp` | ISO 8601 | Normalized UTC timestamp | Extracted from Unix epoch |
| `node` | String | Hardware node ID (e.g., `R02-M1-N0-C:J12-U11`) | `(?P<node>\S+)` |
| `subsys` | String | Subsystem (e.g., `RAS`) | `(?P<subsys>\S+)` |
| `component`| String | Component (e.g., `KERNEL`, `DISCOVERY`) | `(?P<component>\S+)` |
| `level` | String | Severity level (`INFO`, `WARNING`, `ERROR`, `FATAL`) | `(?P<level>\w+)` |
| `message` | String | System event message | Remainder of string |

---

## 3. Data Leakage Prevention Protocols

Data leakage is the most pervasive failure mode in published log anomaly detection papers. LogPulse enforces strict, automated leakage-prevention guarantees:

### 1. Grouped Block Partitioning (HDFS)
- **The Pitfall:** In HDFS, multiple log lines belong to the same block transaction. Randomly splitting individual log lines into train and test causes the model to memorize templates from a block seen in training and test on the same block.
- **The Guarantee:** All log records sharing the same `block_id` are grouped atomically. Partitioning is performed on the set of unique `block_id`s:
  - $\text{Train Blocks} \cap \text{Test Blocks} = \emptyset$
  - $\text{Train Blocks} \cap \text{Val Blocks} = \emptyset$
  - $\text{Val Blocks} \cap \text{Test Blocks} = \emptyset$
- **Unsupervised Cleanliness:** Training sets for baseline unsupervised models (Isolation Forest, DeepLog normal sequences) are strictly populated with known **Normal** blocks to model authentic steady-state operations.

### 2. Strict Chronological Partitioning (BGL)
- **The Pitfall:** Random cross-validation on time-series logs leaks future system states into past training windows, giving models artificially high predictive power.
- **The Guarantee:** Logs are partitioned by strictly ascending temporal order:
  - $\max(\text{Train}_{\text{idx}}) < \min(\text{Val}_{\text{idx}}) < \min(\text{Test}_{\text{idx}})$
  - No future timestamp is ever accessible during training or validation threshold tuning.

### 3. Feature Hygiene
- Ground truth `label` and `is_anomaly` columns are **never** passed into feature engineering pipelines, vectorizers, or model inputs. Labels exist purely as an external oracle for evaluation metrics calculation.

---

## 4. Dataset Artifacts & Checksums

| File Path | Records | Byte Size | SHA256 (First 16 chars) | Role |
| :--- | :--- | :--- | :--- | :--- |
| `data/raw/hdfs/HDFS_2k.log` | 2,000 | 287,848 | `7c967000980c086e` | Raw HDFS benchmark logs |
| `data/raw/hdfs/anomaly_label.csv`| 575,061 | 18,062,492 | `78de297d3862e372` | Ground truth block labels |
| `data/raw/bgl/BGL_2k.log` | 2,000 | 317,150 | `2a819ea540909db6` | Raw BGL benchmark logs |
| `data/processed/hdfs_cleaned.csv` | 2,000 | ~320 KB | Auto-generated | Cleaned HDFS with splits |
| `data/processed/bgl_cleaned.csv` | 2,000 | ~350 KB | Auto-generated | Cleaned BGL with splits |
| `data/processed/hdfs_splits_manifest.json`| - | ~1 KB | Auto-generated | HDFS split audit manifest |
| `data/processed/bgl_splits_manifest.json` | - | ~1 KB | Auto-generated | BGL split audit manifest |

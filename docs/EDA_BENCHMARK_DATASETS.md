# Exploratory Data Analysis & Benchmark Dataset Manifests

Generated: 2026-11-03T09:52:41.876197+00:00  
Author: Data Engineering & MLOps Pipeline  

---

## 1. HDFS Log Dataset (HDFS_2k Benchmark)

### Overview & Data Provenance
- **Source:** Loghub (Hadoop Distributed File System on Amazon EC2 cluster).
- **Log Format:** `Date Time PID Level Component: Message`
- **Identifier:** Hadoop Block ID (`blk_-?[0-9]+`)
- **Ground Truth Labels:** Extracted from official `anomaly_label.csv` (labeled by Hadoop domain experts).

### Dataset Metrics
- **Total Log Records:** 2,000
- **Parsing Validity Rate:** 100.00%
- **Unique Block IDs:** 1,994
  - **Normal Blocks:** 1,926 (96.6%)
  - **Anomalous Blocks:** 68 (3.4%)
- **Lines Per Block Distribution:**
  - Mean: 1.00 lines/block
  - Min: 1 | Median: 1.0 | Max: 2

### Severity Breakdown
```json
{
  "INFO": 1920,
  "WARN": 80
}
```

### Top Active Components
```json
{
  "dfs.FSNamesystem": 659,
  "dfs.DataNode$PacketResponder": 603,
  "dfs.DataNode$DataXceiver": 454,
  "dfs.FSDataset": 263,
  "dfs.DataBlockScanner": 20
}
```

### Leakage-Free Splitting Strategy
- **Partitioning Principle:** Split strictly by **Block ID** to eliminate event co-occurrence leakage.
- **Train Partition:** 1,544 records across 1540 normal blocks (unsupervised baseline).
- **Validation Partition:** 227 records (34 anomalous records).
- **Test Partition:** 229 records (35 anomalous records).
- **Leakage Verification:** Disjoint sets $\text{Train} \cap \text{Test} = \emptyset$, $\text{Train} \cap \text{Val} = \emptyset$ (**PASSED**).

---

## 2. BGL Log Dataset (BGL_2k Benchmark)

### Overview & Data Provenance
- **Source:** Loghub (BlueGene/L Supercomputer at Lawrence Livermore National Laboratory).
- **Log Format:** `Label Epoch Date Node Timestamp Node Subsys Component Level Message`
- **Ground Truth Labels:** Tagged by system administrators (`-` indicates normal, any other tag indicates failure or alert category).

### Dataset Metrics
- **Total Log Records:** 2,000
- **Parsing Validity Rate:** 100.00%
- **Total Anomaly Records:** 143 (7.15%)
- **Total Normal Records:** 1,857

### Severity Breakdown
```json
{
  "INFO": 1597,
  "FATAL": 347,
  "ERROR": 41,
  "WARNING": 8,
  "SEVERE": 7
}
```

### Top Subsystems / Components
```json
{
  "KERNEL": 1820,
  "APP": 107,
  "DISCOVERY": 35,
  "MMCS": 35,
  "HARDWARE": 3
}
```

### Anomaly Category Tags
```json
{
  "-": 1857,
  "KERNDTLB": 60,
  "KERNSTOR": 30,
  "APPSEV": 17,
  "KERNMNTF": 11
}
```

### Chronological Splitting Strategy
- **Partitioning Principle:** Strict chronological order based on log sequence index to ensure temporal realism (zero look-ahead bias).
- **Train Partition (First 80%):** 1,600 records (119 anomalies).
- **Validation Partition (Next 10%):** 200 records (18 anomalies).
- **Test Partition (Final 10%):** 200 records (6 anomalies).
- **Temporal Monotonicity:** $\max(\text{Train}_{\text{idx}}) < \min(\text{Val}_{\text{idx}}) < \min(\text{Test}_{\text{idx}})$ (**PASSED**).

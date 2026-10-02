# Lakebase change-data capture (CDC) — source side

This slice only makes the **source side capturable**. The CDF **consumer**
(`analytics_*` Delta tables) is the next slice and is **not** built here.

## What is configured

`001_operational_schema.sql` sets `REPLICA IDENTITY FULL` on the seven
behavioural tables whose changes drive downstream analytics:

| Table          | Behavioural changes captured |
| :------------- | :--------------------------- |
| `watchlists`   | watch additions/removals     |
| `signals`      | new model predictions        |
| `orders`       | intent → approval → fill     |
| `executions`   | fills                       |
| `positions`    | position/PnL updates         |
| `agent_actions`| every agent tool call        |
| `research_notes`| analyst note CRUD           |

`users` is intentionally excluded — it is reference data, not behavioural.

`REPLICA IDENTITY FULL` means every `UPDATE`/`DELETE` emits the complete old
row image (and the complete new row on update), so the consumer can rebuild
full state without a join back to the primary key. The trade-off is a larger
WAL footprint; that is acceptable for a low-write-frequency operational store.

## What the consumer must subscribe to (next slice)

`wal_level` is already `logical` on `evangoh-capstone-lakebase`. The consumer
must attach to a logical replication publication over these seven tables.

`CREATE PUBLICATION` is **administratively disabled** on this Lakebase instance
(verified: `CREATE PUBLICATION is not enabled on this Lakebase instance`), so
the publication and replication slot must be provisioned by the Databricks
Lakebase CDC layer rather than by this migration. When it is provisioned, the
publication must include exactly:

```
publication: lakebase_cdc
tables: watchlists, signals, orders, executions, positions, agent_actions, research_notes
```

The consumer must also create a dedicated replication slot and consume it with
a committed, persisted LSN so restarts never miss or duplicate rows.

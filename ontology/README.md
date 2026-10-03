# Analytics ontology

These YAML files are the machine-readable vocabulary for NL analytics and point-in-time feature use. `table_semantics.yaml` is the table registry; references in filters, joins, metrics, and the SEC knowledge graph must resolve to that registry.

All analytical joins are point-in-time: select only rows whose `information_available_ts` is at or before the query or prediction timestamp. At source and silver layers, use the documented native availability timestamp (`accepted_ts`, `release_ts`, `participant_ts`, or a bar-close timestamp) to derive that canonical field. Never substitute business dates such as `filing_date`, `report_date`, or `observation_date` for availability.

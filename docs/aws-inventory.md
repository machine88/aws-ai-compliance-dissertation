# Read-only inventory procedure

Verify the configured identity, expected account and approved region before live reads. Reject root sessions. Use AWS MCP to inspect Config recorders, delivery channels, rule configuration, Security Hub CSPM enrollment, existing CloudTrail trails, bucket locations, service-linked roles and budget configuration. Do not read bucket objects or production data.

Keep raw responses and actual inventory findings under the ignored evidence/inventory directory. They are operational preparation, not pilot or confirmatory observations, and must not be published in the public source repository. A denied or malformed response does not establish that a service is absent. Inventory must be repeated immediately before any approved deployment.

The Phase 2 code assumes a fresh baseline. If actual inventory finds existing services or matching bucket names, stop and review adoption or import rather than replacing them. No account resource should be changed by this procedure.

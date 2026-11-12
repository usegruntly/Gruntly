# Agent tasks pilot

| task | workload | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said |
|---|---|---|---|---|---|---|---|---|---|---|
| read_invoke_callers | code_reading | alone | 1.00 | yes | 0.084 | 0.084 | 0.0000 | 4 | 13 | - |
| read_invoke_callers | code_reading | forced | 1.00 | yes | 0.084 | 0.081 | 0.0030 | 3 | 28 | 70% |
| read_invoke_callers | code_reading | haiku_alone | 1.00 | yes | 0.003 | 0.003 | 0.0000 | 2 | 11 | - |
| read_paramtype_names | code_reading | alone | 1.00 | yes | 0.079 | 0.079 | 0.0000 | 5 | 17 | - |
| read_paramtype_names | code_reading | forced | 1.00 | yes | 0.077 | 0.075 | 0.0028 | 3 | 31 | 65% |
| read_paramtype_names | code_reading | haiku_alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 3 | 13 | - |
| wrangle_events_conversion | data_wrangle | alone | 1.00 | yes | 0.067 | 0.067 | 0.0000 | 4 | 14 | - |
| wrangle_events_conversion | data_wrangle | forced | 1.00 | yes | 0.066 | 0.059 | 0.0069 | 2 | 24 | 70% |
| wrangle_events_conversion | data_wrangle | haiku_alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 4 | 16 | - |
| wrangle_orders_revenue | data_wrangle | alone | 1.00 | yes | 0.068 | 0.068 | 0.0000 | 4 | 19 | - |
| wrangle_orders_revenue | data_wrangle | forced | 1.00 | yes | 0.077 | 0.070 | 0.0072 | 3 | 31 | 80% |
| wrangle_orders_revenue | data_wrangle | haiku_alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 4 | 15 | - |
| fetch_rfc10075_snac_bit | exact_fetch | alone | 1.00 | yes | 0.063 | 0.063 | 0.0000 | 3 | 12 | - |
| fetch_rfc10075_snac_bit | exact_fetch | forced | 1.00 | yes | 0.060 | 0.057 | 0.0028 | 2 | 25 | 60% |
| fetch_rfc10075_snac_bit | exact_fetch | haiku_alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 2 | 10 | - |
| fetch_rfc9995_cose_labels | exact_fetch | alone | 1.00 | yes | 0.087 | 0.087 | 0.0000 | 4 | 14 | - |
| fetch_rfc9995_cose_labels | exact_fetch | forced | 1.00 | yes | 0.084 | 0.082 | 0.0023 | 5 | 36 | 60% |
| fetch_rfc9995_cose_labels | exact_fetch | haiku_alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 2 | 10 | - |
| control_rfc6455_opcodes | memorised_control | alone | 1.00 | yes | 0.055 | 0.055 | 0.0000 | 2 | 10 | - |
| control_rfc6455_opcodes | memorised_control | forced | 1.00 | yes | 0.074 | 0.059 | 0.0147 | 2 | 46 | 88% |
| control_rfc6455_opcodes | memorised_control | haiku_alone | 1.00 | yes | 0.003 | 0.003 | 0.0000 | 1 | 7 | - |
| summarise_changelog_breaking | summarise | alone | 1.00 | yes | 0.093 | 0.093 | 0.0000 | 6 | 18 | - |
| summarise_changelog_breaking | summarise | forced | 1.00 | yes | 0.078 | 0.075 | 0.0030 | 3 | 26 | 80% |
| summarise_changelog_breaking | summarise | haiku_alone | 1.00 | yes | 0.009 | 0.009 | 0.0000 | 3 | 9 | - |
| summarise_incident_log | summarise | alone | 1.00 | yes | 0.078 | 0.078 | 0.0000 | 5 | 17 | - |
| summarise_incident_log | summarise | forced | 1.00 | yes | 0.082 | 0.079 | 0.0030 | 5 | 32 | 60% |
| summarise_incident_log | summarise | haiku_alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 4 | 16 | - |
| research_jscontact_registry | web_research | alone | 1.00 | yes | 0.108 | 0.108 | 0.0000 | 6 | 30 | - |
| research_jscontact_registry | web_research | forced | 1.00 | yes | 0.096 | 0.077 | 0.0185 | 3 | 60 | 55% |
| research_jscontact_registry | web_research | haiku_alone | 1.00 | yes | 0.018 | 0.018 | 0.0000 | 5 | 31 | - |
| research_oauth_audience | web_research | alone | 1.00 | yes | 0.130 | 0.130 | 0.0000 | 6 | 41 | - |
| research_oauth_audience | web_research | forced | 0.83 | NO | 0.086 | 0.066 | 0.0198 | 2 | 54 | 40% |
| research_oauth_audience | web_research | haiku_alone | 1.00 | yes | 0.032 | 0.032 | 0.0000 | 6 | 33 | - |

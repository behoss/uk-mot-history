# UK first-MOT fail rates by make and model (2022–2024)

[`uk-first-mot-fail-rates-2022-2024.csv`](uk-first-mot-fail-rates-2022-2024.csv): how often each make and model fails its
**first MOT** (the test at three years old), built from DVSA's anonymised MOT test results for 2022 to 2024. 350 models,
7,348,122 first MOTs, a national first-MOT fail rate of 12.3%.

| Column | Meaning |
|---|---|
| `make`, `model`, `segment` | Vehicle and its market segment |
| `first_mot_tests` | First MOTs (age 3) in the period |
| `first_mot_fail_rate_pct` | Share that failed first time (PRS counts as a fail, the industry standard) |
| `times_national_rate` | Fail rate divided by the national first-MOT rate (1.00 = average) |
| `median_miles_at_first_mot` | Median odometer reading at the first MOT |
| `all_ages_fail_rate_pct` | First-time fail rate across every age |
| `all_ages_vs_same_age_and_mileage_pct` | Against cars of the same age and mileage band (negative = better than average) |
| `ranked` | `yes` when the model has enough tests to rank |
| `page` | That model's full reliability page: common faults, fail rate by year, what to check |

The ranked tables, charts and method are on
[Cars most likely to fail their first MOT](https://getfreecarcheck.co.uk/research/first-mot-fail-rates) at
GetFreeCarCheck. Archived copy with a DOI: [10.5281/zenodo.24358242](https://doi.org/10.5281/zenodo.24358242).

Licence: Contains public sector information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) (DVSA MOT
test results). Reuse it freely with that attribution and a link to the research page above.

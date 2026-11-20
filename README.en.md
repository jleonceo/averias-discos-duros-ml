Versión en español: [README.md](README.md)

# Hard drive failure prediction and purchase cost (Backblaze, 2020-2026)

A data analysis and machine learning project built on Backblaze's public hard drive records. Backblaze is a cloud storage provider. The project answers two operational questions: which drive model is cheapest per terabyte once failures are taken into account, and which drives should be checked each month before they fail.

## Key results

- **Which model to buy:** the purchase price accounts for **93.56%** of the cost per terabyte per year, and failures for the rest. This is the median across 27 models, that is, the figure for the model in the middle when they are ranked. In all seven comparable purchase groups (same year, same capacity), the cheapest model per terabyte is also the one that fails least.
- **Which drives to check:** a machine learning model produces a monthly list of the 100 drives most likely to fail in the next 30 days. On average it catches **22.6 failures a month**, **52% more** than the five SMART warnings rule, which ranks drives by how many failure counters are above zero. This was measured over the 11 months held back for the final test, July 2025 to May 2026.
- **What to monitor:** the annualized failure rate rises with every year of age from the first to the fifth, from 0.79% to 2.58%. The sac2 data center in Sacramento fails 10% more than expected for its mix of models and ages.

[![CI](https://github.com/jleonceo/averias-discos-duros-ml/actions/workflows/ci.yml/badge.svg)](https://github.com/jleonceo/averias-discos-duros-ml/actions/workflows/ci.yml)

## Methodology

A snapshot is the state of a drive on the first day of a month: its SMART counters, model, capacity and data center. Snapshots are the unit used throughout data cleaning and modeling.

1. **Data quality:** issues were diagnosed and fixed before any analysis. For example, 2,729 snapshots with a capacity of -1 or 0.1 TB were given the capacity of their model, and four model names written with a double space were merged.
2. **Cost analysis:** the cost per terabyte per year of each model has two parts. The first is the purchase price, spread over a 6-year service life. The second is the annualized failure rate multiplied by the cost of each replacement: a new drive plus $37 of labor. Prices are those published by Backblaze up to 2022 and estimated from 2023 onwards.
3. **Feature preparation:** each snapshot carries the drive's age and how much each counter has changed since the previous month's snapshot.
4. **Modeling and validation:** three model types were compared over five quarterly folds. The winner was a HistGradientBoosting model, a gradient-boosted decision tree ensemble. It was validated on the following twelve months, and the last year was kept untouched until the final test.
5. **Production:** one monthly process scores the new snapshot without dropping any drive (drives that cannot be scored are kept with the reason), and another retrains the model on new data.

## Limitations

- Estimated prices: drive prices from 2023 onwards are estimates, so the cost per terabyte is only as good as those estimates.
- Failures without warning: 32% of the failures in the final-test year showed no warning at all on the first day of the month. The five SMART warnings rule cannot flag them, and they are the hardest cases for the risk list to anticipate.
- The last month: the data run to June 2026, but the list's final test ends in May. Knowing whether a June drive failed within the next 30 days would require July data, which do not exist yet.
- Spare parts: forecasting by model and age does not beat simply repeating the previous quarter's failures. In the final-test year, its mean error was 31.8%, against 30.6%.
- The model in use: it was retrained with one more year of data and measured on the final-test year before being approved. For that model, the year is no longer an independent test.

## Outputs

- **Final report:** ten pages for the head of operations, with five decisions for approval ([`informes/informe_final.html`](https://jleonceo.github.io/averias-discos-duros-ml/informes/informe_final.html)). In Spanish.
- **Dashboard:** five tabs with filters by data center, manufacturer, capacity and age, plus the month's risk list as a CSV download ([`informes/cuadro_mando.html`](https://jleonceo.github.io/averias-discos-duros-ml/informes/cuadro_mando.html)). In Spanish.
- **The six problems:** how this project dealt with the six problems that come up in every data project ([`informes/los_seis_problemas.md`](informes/los_seis_problemas.md)). In Spanish.

## Repository layout

- `preparacion_datos/`: the two scripts that extract the working data from Backblaze's files and set aside the final-test year, each with its own test.
- `scripts/`: the chain of 22 scripts, numbered in process order, from the raw data to the final report and the dashboard. Each script's header states what it reads, what it writes and how to run it.
- `tests/`: one test suite per script, each including cases that must fail.
- `produccion/`: the monthly scoring process and the retraining.
- `modelos/`: the model in use and its metadata.
- `informes/`: the final report, the dashboard, the six problems and the report from each step.
- `config/`: the business and transformation rules, and the decisions the scripts read.

## The data

The data are not included in this repository. They are public: Backblaze, [Drive Stats](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data), the daily record of every drive in its data centers. Backblaze's terms ask users to credit Backblaze as the source and not to sell the data. These are drive records: no column refers to a person.

What was done with them:

1. **Download:** the 26 quarterly files, from `data_Q1_2020.zip` to `data_Q2_2026.zip`, about 25 GB. Each contains one CSV per day, with one row per drive.
2. **Extract:** `podar_datos.py` keeps a snapshot of every drive on the first day of each month, the 30 days before each failure, the list of failures and a daily count of drives and failures by model, capacity and data center. It drops the 68 columns that are empty or constant. It takes about two and a half hours.
3. **Final-test year:** `apartar_reserva.py` sets aside everything from 1 July 2025 to 30 June 2026, which was not looked at until the end. That leaves 17,960 failures for the analysis and 4,751 for the final test.

Script `10` also reads the revenue tables from Backblaze's 2025 annual report, its [Form 10-K filed with the SEC](https://www.sec.gov/Archives/edgar/data/1462056/000162828026016395/blze-20251231.htm). It is a third-party document and is not included either: the script expects it at `config/sector/documentos/16_backblaze_10k_2025_tablas_ingresos.txt`.

## How to run it

You need conda and the environment in `environment.yml`:

```bash
git clone https://github.com/jleonceo/averias-discos-duros-ml.git && cd averias-discos-duros-ml
conda env create -f environment.yml && conda activate 68_averias_discos_duros
python -W error tests/probar_17_informe_final.py
```

The last command runs the final report's test, which does not need the data: it reads the reports included in the repository. Without the data, 14 of the 28 tests in `tests/` pass; the others read the Backblaze extract. To rerun the whole project, with the ZIP files downloaded into a `zips/` folder:

```bash
python preparacion_datos/podar_datos.py data/poda_entera zips/data_Q*.zip
python -I preparacion_datos/apartar_reserva.py data/poda_entera data/raw/podado data/raw/reserva
```

Then run the scripts in `scripts/` in order, from `01` to `22`, as each script's header describes.

## Related repositories

- [prediccion-cancelaciones-hotel-ml](https://github.com/jleonceo/prediccion-cancelaciones-hotel-ml): ranking hotel bookings by their risk of ending without check-in, using the same structure of script chain, reports and production.
- [reposicion-inventario-prevision-ml](https://github.com/jleonceo/reposicion-inventario-prevision-ml): a daily decision backed by a forecast, measured on a half-year held back for the final test.
- [store-sales-forecasting-ml](https://github.com/jleonceo/store-sales-forecasting-ml): sales forecasting with time-based validation and simulated batch deployment.

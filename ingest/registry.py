"""Registry of the real, public datasets used by AEROGUARD TRUST.

No data is generated. Every dataset is downloaded from its official source,
checked against the publisher's SHA-256 when one is published, and credited.
Raw data lives in data/raw/ and is never committed.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RemoteFile:
    name: str
    url: str
    sha256: str | None = None  # publisher-provided hash, when available
    extract: bool = False      # archive to unpack (zip / rar / 7z via system tar)


@dataclass(frozen=True)
class Dataset:
    id: str
    title: str
    source: str
    page: str
    license: str
    citation: str
    used_for: str
    doi: str | None = None
    files: tuple[RemoteFile, ...] = field(default_factory=tuple)


_MENDELEY = "https://data.mendeley.com/public-files/datasets/{ds}/files/{fid}/file_downloaded"


def _m(ds: str, fid: str) -> str:
    return _MENDELEY.format(ds=ds, fid=fid)


DATASETS: dict[str, Dataset] = {d.id: d for d in [
    Dataset(
        id="industrial_hall_fire",
        title="Indoor Fire Dataset with Distributed Multi-Sensor Nodes (Industrial Hall)",
        source="Mendeley Data", page="https://data.mendeley.com/datasets/yghykzm4km/1",
        doi="10.17632/yghykzm4km.1", license="CC BY 4.0",
        citation="Indoor Fire Dataset with Distributed Multi-Sensor Nodes (Industrial Hall), Mendeley Data, V1, 2024. doi:10.17632/yghykzm4km.1",
        used_for="Zone sensor model: incipient fires (incl. cable fire) vs industrial nuisances (welding, abrasive cutting, exhaust).",
        files=(RemoteFile("industrial_hall.csv", _m("yghykzm4km", "ac22049a-6c73-4276-8583-05b2cf735601"),
                          "b431b611a44e4282510bd53158aaa71512554481433d8f3a90f9475c17134839"),),
    ),
    Dataset(
        id="indoor_lab_fire",
        title="Indoor Laboratory Fire Dataset",
        source="Mendeley Data (Zayed University)", page="https://data.mendeley.com/datasets/f3mjnbm9b3/1",
        doi="10.17632/f3mjnbm9b3.1", license="CC BY 4.0",
        citation="Nazir, A. et al. Indoor Laboratory Fire Dataset, Mendeley Data, V1, 2021. doi:10.17632/f3mjnbm9b3.1; "
                 "paper: Early Fire Detection: A New Indoor Laboratory Dataset and Data Distribution Analysis, Fire 2022, 5(1), 11.",
        used_for="Detection lead time on electrical fires before the conventional alarm.",
        files=tuple(RemoteFile(n, _m("f3mjnbm9b3", fid), h) for n, fid, h in [
            ("carton_1.csv", "3a331357-047a-4f93-9648-299eed7656bc", "3e298c5c795926c6780dc264ad8612544d90d85475e40f5403432a12b4e08c7b"),
            ("carton_2.csv", "06ce2e84-a6aa-40e3-baaf-2e05cb9b7436", "2e2126094dec720bf6dcc47273627b2a29805d9ab2b1d14914ea703f5fab5b87"),
            ("clothing_1.csv", "5da73ca2-7c88-4af9-b483-5677c68841bb", "b1e6251f43f319c2d59b87aa8abeb5270a7daee2d4105981fa1564e6634507a9"),
            ("clothing_2.csv", "d37c099c-26c6-411f-bdf3-07936e39efe5", "d0212c9e67c17854dda54d9d2a75304add614a3b79bc6bc9462b981ef0751533"),
            ("electrical_1.csv", "b8437d1a-0df2-463a-a90a-667ec65a38b3", "fbcd0f53ad28914135f268db5f5225c115f57fc3e42055f8b0ac79a78afb57ce"),
            ("electrical_2.csv", "f5dd7415-6a18-4872-bcf4-852252c81b37", "622bf5fadcbc93face503cbf6cc41d4ef164a8691e755ab59d5debb88635cc8c"),
            ("electrical_3.csv", "bb004e1a-eeba-4f79-bbe5-27186165caf1", "e12763154893a6f429fe9e78d41d8d9d45324eecf4970dec6b167e4b716759aa"),
            ("electrical_4.csv", "e8292cf4-29fb-4cbe-b8ae-db57adf8afdd", "c3547b6693c3b8fe56fc5e69ca540bc2e81e244d90a7a1d43fe8bd9d1566780d"),
        ]),
    ),
    Dataset(
        id="test_chamber_fire",
        title="Indoor Fire Dataset of Multi Sensor Data (Small Scale Test Chamber)",
        source="Mendeley Data", page="https://data.mendeley.com/datasets/m85f9h6g9j/1",
        doi="10.17632/m85f9h6g9j.1", license="CC BY 4.0",
        citation="Indoor Fire Dataset of Multi Sensor Data (Small Scale Test Chamber), Mendeley Data, V1, 2024. doi:10.17632/m85f9h6g9j.1",
        used_for="Fire escalation stages (intensity 1-6) for the risk engine.",
        files=(RemoteFile("test_chamber.csv", _m("m85f9h6g9j", "29a2fde9-469a-4ed6-add7-006f8edd8c2c"),
                          "11083fa8db6c4dc96abaa11b4e92b3bb28361945702f0543df194e155726958b"),),
    ),
    Dataset(
        id="skab",
        title="SKAB - Skoltech Anomaly Benchmark (water-pump testbed)",
        source="GitHub waico/SKAB", page="https://github.com/waico/SKAB",
        doi="10.34740/KAGGLE/DSV/1693952", license="GPL-3.0",
        citation="Katser, I. D., Kozitsin, V. O. Skoltech Anomaly Benchmark (SKAB), Kaggle, 2020. doi:10.34740/KAGGLE/DSV/1693952",
        used_for="Motor anomaly model: vibration, motor current, temperature, pressure with labelled anomalies.",
        files=(RemoteFile("skab.zip", "https://github.com/waico/SKAB/archive/refs/heads/master.zip", extract=True),),
    ),
    Dataset(
        id="metropt3",
        title="MetroPT-3 Dataset (metro train air compressor)",
        source="UCI Machine Learning Repository", page="https://archive.ics.uci.edu/dataset/791/metropt+3+dataset",
        doi="10.24432/C5VW3R", license="CC BY 4.0",
        citation="Veloso, B., Gama, J., Ribeiro, R., Pereira, P. MetroPT-3 Dataset, UCI Machine Learning Repository, 2023. doi:10.24432/C5VW3R",
        used_for="Compressor model: early detection of real failures documented in maintenance reports.",
        files=(RemoteFile("metropt3.zip", "https://archive.ics.uci.edu/static/public/791/metropt+3+dataset.zip", extract=True),),
    ),
    Dataset(
        id="motor_thermal",
        title="Thermal image of equipment (Induction Motor) + 40 Ground Truths",
        source="Mendeley Data (Babol Noshirvani University of Technology)", page="https://data.mendeley.com/datasets/m4sbt8hbvk/3",
        doi="10.17632/m4sbt8hbvk.3", license="CC BY 4.0",
        citation="Najafi, M. et al. Thermal image of equipment (Induction Motor), Mendeley Data, V3, 2023. doi:10.17632/m4sbt8hbvk.3",
        used_for="Drone thermal inspection: hotspot detection on real equipment infrared images.",
        files=(
            RemoteFile("IR-Motor-bmp.rar", _m("m4sbt8hbvk", "b189b1c9-8200-4429-a425-4c45ebecc211"),
                       "443815d41f96baf971008687eb2a80e7bc21ca7bfc3dc61cb8fa7ad9295020ea", extract=True),
            RemoteFile("40_GT_with_Refrences.rar", _m("m4sbt8hbvk", "27cff315-26ba-4fbd-908f-90e0c04298d6"),
                       "d1e7780293c1f9ea48c5e524d6b751b32056bc8579c20927a511d7d3e874f51d", extract=True),
            RemoteFile("Readme_InductionMotor.pdf", _m("m4sbt8hbvk", "aaf7a501-6935-4b3e-ad63-144eb752a0de"),
                       "61cad70b6113d341ab8ac969c64c7c18a553c39a42747f9ceeaa7a57eedf0054"),
        ),
    ),
    Dataset(
        id="aria",
        title="ARIA - industrial accidents database (BARPI, France), 2020 snapshot",
        source="data.gouv.fr", page="https://www.data.gouv.fr/datasets/analyse-recherche-et-information-sur-les-accidents",
        license="Licence Ouverte 2.0 (data.gouv.fr copy); source data published by BARPI",
        citation="BARPI, base ARIA (Analyse, Recherche et Information sur les Accidents), extraction publiée sur data.gouv.fr, 2020-10-12.",
        used_for="Real industrial accident statistics (causes, sectors, consequences) until the Protection Civile data arrives.",
        files=(RemoteFile("aria.xlsx", "https://static.data.gouv.fr/resources/analyse-recherche-et-information-sur-les-accidents/20201012-123758/aria.xlsx"),),
    ),
]}

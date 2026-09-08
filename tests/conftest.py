"""Fixtures partagées pour les tests AppTest de l'app Streamlit.

AppTest exécute le script via ``exec()`` direct (pas via ``import``), donc
patcher ``app.streamlit_app.run_ocr_raw`` est inefficace : le script crée
ses propres fonctions dans son propre namespace.

Solution : patcher à un niveau plus profond — la CLASSE
``PaddleOCREngine`` (importée par le script). Quand le script appelle
``load_paddleocr_engine()`` puis ``engine.read(...)``, il obtient notre
mock. Pareil pour ``cv2.imread`` et ``streamlit.file_uploader``.
"""
from __future__ import annotations
import os
from typing import Callable
import pytest
import numpy as np


# En mode test, bypass le gate "click Générer devis" qui maintenant
# précède le pipeline OCR (UX V1.2 — l'user clique pour déclencher).
# Tous les 45 tests AppTest reposent sur le pipeline auto-déclenché.
os.environ["STREAMLIT_TEST_AUTO_TRIGGER"] = "1"


# ============================================================================
# Fake uploaded file
# ============================================================================


class FakeUploadedFile:
    """Simule un Streamlit UploadedFile."""

    def __init__(self, content: bytes, name: str = "test_plan.png"):
        self._content = content
        self.name = name
        self.size = len(content)
        self.type = "image/png"

    def read(self) -> bytes:
        return self._content

    def getvalue(self) -> bytes:
        return self._content

    def seek(self, pos: int) -> None:
        pass


def _make_fake_png_bytes() -> bytes:
    import cv2
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


FAKE_IMG_BYTES = _make_fake_png_bytes()
FAKE_IMG_ARRAY = np.zeros((100, 100, 3), dtype=np.uint8)


# ============================================================================
# Mock OCR data — plan résidentiel typique 7 pièces
# ============================================================================
# Format : list[dict] avec text + bbox + confidence
# Les aliases FR sont reconnus par postprocess_ocr_items → room_type set.

MOCK_OCR_RESIDENTIAL = [
    {"text": "Cuisine", "bbox": [[100, 100], [200, 100], [200, 150], [100, 150]], "confidence": 0.95},
    {"text": "Séjour", "bbox": [[300, 100], [400, 100], [400, 150], [300, 150]], "confidence": 0.93},
    {"text": "Chambre", "bbox": [[500, 100], [600, 100], [600, 150], [500, 150]], "confidence": 0.92},
    {"text": "Chambre", "bbox": [[100, 300], [200, 300], [200, 350], [100, 350]], "confidence": 0.91},
    {"text": "SDB", "bbox": [[300, 300], [400, 300], [400, 350], [300, 350]], "confidence": 0.89},
    {"text": "WC", "bbox": [[500, 300], [600, 300], [600, 350], [500, 350]], "confidence": 0.85},
    {"text": "Dégagement", "bbox": [[100, 500], [200, 500], [200, 550], [100, 550]], "confidence": 0.90},
]


# ============================================================================
# Mock engine class
# ============================================================================


class MockPaddleOCREngine:
    """Mock de PaddleOCREngine — pas de chargement modèle, .read() retourne
    les OCR pré-définis dans la fixture."""

    _next_ocr_data: list[dict] = MOCK_OCR_RESIDENTIAL  # class-level, set by fixture

    def __init__(self, *args, **kwargs):
        # Pas de chargement de modèle ML
        pass

    def read(self, img_bgr, preprocess: bool = True, detect_vertical: bool = True):
        return MockPaddleOCREngine._next_ocr_data


# ============================================================================
# Auto-clear Streamlit caches between tests
# ============================================================================


@pytest.fixture(autouse=True)
def _clear_streamlit_caches():
    """Streamlit cache_data + cache_resource persistent entre tests dans le
    même process Python. Sans clear, les fixtures d'un test précédent
    contaminent les suivants (engine déjà cached avec mauvaises données)."""
    import streamlit as st
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


# ============================================================================
# Fixture principale : patche tout ce qu'il faut
# ============================================================================


@pytest.fixture
def patch_pipeline(monkeypatch) -> Callable[..., None]:
    """Patche file_uploader + OCR engine + cv2.imread.

    Doit être appelé AVANT ``AppTest.from_file(...)``.

    Usage::

        def test_xxx(patch_pipeline):
            patch_pipeline()  # OCR résidentiel par défaut
            at = AppTest.from_file("app/streamlit_app.py")
            at.run()

    Override OCR data: ``patch_pipeline(custom_ocr=[...])``.
    """
    def apply(custom_ocr: list[dict] | None = None) -> None:
        ocr_data = custom_ocr if custom_ocr is not None else MOCK_OCR_RESIDENTIAL
        # Set la donnée de classe avant l'instanciation
        MockPaddleOCREngine._next_ocr_data = ocr_data

        fake_file = FakeUploadedFile(FAKE_IMG_BYTES)

        # 1. Patch st.file_uploader (utilisé dans sidebar)
        import streamlit as st
        monkeypatch.setattr(
            st, "file_uploader",
            lambda *args, **kwargs: fake_file,
        )

        # 2. Patch PaddleOCREngine class — la source de vérité pour l'OCR.
        # Le script app fait `from src.planrec.ocr.engine_paddle import
        # PaddleOCREngine` et instancie via load_paddleocr_engine(). En
        # patchant la classe, toute instance créée est notre mock.
        from src.planrec.ocr import engine_paddle
        monkeypatch.setattr(engine_paddle, "PaddleOCREngine", MockPaddleOCREngine)

        # 3. Patch cv2.imread (utilisé pour overlay rendering depuis tmp_path)
        import cv2
        monkeypatch.setattr(cv2, "imread", lambda *args, **kwargs: FAKE_IMG_ARRAY)

    return apply


# ============================================================================
# Helpers d'inspection / interaction
# ============================================================================


def find_img_hash(at) -> str:
    """Extrait l'img_hash (12 hex) depuis les KEYS de boutons.

    Les boutons exposent ``.key`` (ex: 'devis_editor_HASH_add'). On utilise
    cette source car ``at.session_state.keys()`` n'est pas supporté.
    """
    for b in at.button:
        key = b.key
        if key and key.startswith("devis_editor_") and key.endswith("_add"):
            # Format : devis_editor_HASH_add
            return key.replace("devis_editor_", "").replace("_add", "")
    raise ValueError(
        f"img_hash non trouvé via boutons. Boutons disponibles : "
        f"{[(b.label, b.key) for b in at.button]}"
    )


def get_editor_df(at):
    """DataFrame éditeur Pièces."""
    img_hash = find_img_hash(at)
    return at.session_state[f"devis_editor_{img_hash}"]


def get_devis_df(at):
    """DataFrame tableau devis (None si pas généré)."""
    img_hash = find_img_hash(at)
    key = f"devis_lines_{img_hash}"
    try:
        return at.session_state[key]
    except KeyError:
        return None


def find_button_by_label(at, label_substr: str):
    """Trouve un bouton par sous-chaîne de label (case-insensitive)."""
    substr = label_substr.lower()
    matches = [b for b in at.button if substr in b.label.lower()]
    if not matches:
        labels = [b.label for b in at.button]
        raise ValueError(
            f"Bouton avec label contenant '{label_substr}' non trouvé. "
            f"Boutons présents : {labels}"
        )
    return matches[0]


def find_selectboxes_by_label(at, exact_label: str):
    """Retourne tous les selectbox dont le label matche exactement."""
    return [s for s in at.selectbox if s.label == exact_label]


def get_equipments_state(at):
    """Return equipments_state list in session_state, or None if absent."""
    try:
        img_hash = find_img_hash(at)
    except ValueError:
        return None
    key = f"equipments_state_{img_hash}"
    try:
        return at.session_state[key]
    except KeyError:
        return None

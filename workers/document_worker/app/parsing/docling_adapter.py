"""Wraps the three cascade levels (spec's cheap-first parser cascade) as real
Docling pipeline-option variations.

Docling's `PdfPipelineOptions` apply to a whole conversion, not to individual
pages within one `convert()` call — there is no supported way to run OCR on
only page 7 of a document in a single pass. So this cascade escalates the
*whole document* to the next level whenever the previous level's page-quality
check (see `pipeline.py`) flags any page as needing it. This still satisfies
the "never OCR/VLM every page unconditionally" rule (spec §101): Level 1
(cheapest, OCR off) is always tried first, and Level 2/3 only run when
triggered by an actual quality failure.
"""

import enum
import sys
from pathlib import Path

import transformers.core_model_loading as _core_model_loading
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    RapidOcrOptions,
    TableFormerMode,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.io import DocumentStream

# Windows fix: transformers' parallel weight-materialization thread pool
# (used when Docling's layout model loads via `from_pretrained`) crashes with
# "Windows fatal exception: access violation" when torch tensor copies run on
# a background thread on this platform's Python build (reproduced on this
# repo's Windows dev machine — confirmed to disappear with a single worker).
# Forcing single-threaded weight loading only slows the one-time model load
# per worker process, not per-document parsing.
if sys.platform == "win32":
    _core_model_loading.GLOBAL_WORKERS = 1


class ParserLevel(int, enum.Enum):
    LEVEL_1_NATIVE = 1
    LEVEL_2_LAYOUT_TABLE = 2
    LEVEL_3_OCR = 3


def _pipeline_options_for(level: ParserLevel) -> PdfPipelineOptions:
    options = PdfPipelineOptions()
    if level is ParserLevel.LEVEL_1_NATIVE:
        options.do_ocr = False
        options.do_table_structure = False
    elif level is ParserLevel.LEVEL_2_LAYOUT_TABLE:
        options.do_ocr = False
        options.do_table_structure = True
        options.table_structure_options.mode = TableFormerMode.ACCURATE
    else:
        options.do_ocr = True
        options.do_table_structure = True
        options.table_structure_options.mode = TableFormerMode.ACCURATE
        options.ocr_options = RapidOcrOptions(force_full_page_ocr=True)
    return options


def convert(source: Path | DocumentStream, level: ParserLevel) -> ConversionResult:
    """Run Docling conversion at the given cascade level."""
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=_pipeline_options_for(level))
        }
    )
    return converter.convert(source)

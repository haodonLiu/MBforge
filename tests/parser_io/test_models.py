import pytest
from dataclasses import asdict
from mbforge.parser_io.models import ParseResult, MoleculeData, SARTask


def test_parse_result_creation():
    result = ParseResult(
        status="success",
        token="abc123",
        raw_data={"key": "value"},
    )
    assert result.status == "success"
    assert result.token == "abc123"
    assert result.raw_data == {"key": "value"}


def test_parse_result_to_dict():
    result = ParseResult(
        status="success",
        token="abc123",
        raw_data={"key": "value"},
    )
    d = asdict(result)
    assert d["status"] == "success"
    assert d["token"] == "abc123"


def test_molecule_data_creation():
    mol = MoleculeData(
        smiles="CCO",
        name="ethanol",
        activity=10.5,
        source="page 1",
    )
    assert mol.smiles == "CCO"
    assert mol.name == "ethanol"
    assert mol.activity == 10.5
    assert mol.source == "page 1"


def test_molecule_data_optional_activity():
    mol = MoleculeData(smiles="CCO", name="ethanol")
    assert mol.activity is None


def test_sar_task_creation():
    molecules = [
        MoleculeData(smiles="CCO", name="ethanol", activity=10.0),
        MoleculeData(smiles="CC", name="ethane", activity=20.0),
    ]
    task = SARTask(molecules=molecules, metadata={"source": "test.pdf"})
    assert len(task.molecules) == 2
    assert task.metadata["source"] == "test.pdf"


def test_sar_task_empty_molecules():
    task = SARTask(molecules=[], metadata={})
    assert len(task.molecules) == 0

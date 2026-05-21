"""化学数据库 API 客户端模块.

本模块提供通过在线 API 查询小分子化合物属性、结构和标识符的功能。
支持 PubChem PUG REST API 和 NCI/NIH Chemical Identifier Resolver (CIR)。

主要类:
    CompoundProperties: 化合物属性数据模型
    CompoundInfo: 化合物综合信息数据模型
    PubChemClient: PubChem API 客户端
    NCICIRClient: NCI CIR API 客户端
    ChemicalAPIClient: 统一 API 客户端入口

示例:
    >>> client = ChemicalAPIClient()
    >>> info = client.get_compound_info("CC(=O)Oc1ccccc1C(=O)O")
    >>> print(info.properties.molecular_weight)
    180.16
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# PubChem 支持的属性列表（常用子集）
PUBCHEM_COMMON_PROPERTIES = (
    "MolecularFormula,MolecularWeight,CanonicalSMILES,IsomericSMILES,"
    "InChI,InChIKey,IUPACName,XLogP,ExactMass,TPSA,Complexity,"
    "Charge,HBondDonorCount,HBondAcceptorCount,RotatableBondCount,"
    "HeavyAtomCount,CovalentUnitCount"
)


class APIClientError(Exception):
    """API 客户端错误.

    当 HTTP 请求失败、API 返回错误或数据解析失败时抛出此异常。
    """

    pass


@dataclass
class CompoundProperties:
    """化合物理化属性数据模型.

    属性:
        molecular_formula: 分子式.
        molecular_weight: 分子量.
        canonical_smiles: Canonical SMILES.
        isomeric_smiles: 异构体 SMILES.
        inchi: InChI 标识符.
        inchi_key: InChIKey 哈希.
        iupac_name: IUPAC 系统命名.
        xlogp: 脂水分配系数预测值.
        exact_mass: 精确分子量.
        tpsa: 拓扑极性表面积（Å²）.
        complexity: 结构复杂度指数.
        charge: 形式电荷.
        hbd_count: 氢键供体数.
        hba_count: 氢键受体数.
        rotatable_bond_count: 可旋转键数.
        heavy_atom_count: 重原子数.
        covalent_unit_count: 共价单元数.
    """

    cid: Optional[int] = None
    molecular_formula: Optional[str] = None
    molecular_weight: Optional[float] = None
    canonical_smiles: Optional[str] = None
    isomeric_smiles: Optional[str] = None
    inchi: Optional[str] = None
    inchi_key: Optional[str] = None
    iupac_name: Optional[str] = None
    xlogp: Optional[float] = None
    exact_mass: Optional[float] = None
    tpsa: Optional[float] = None
    complexity: Optional[float] = None
    charge: Optional[int] = None
    hbd_count: Optional[int] = None
    hba_count: Optional[int] = None
    rotatable_bond_count: Optional[int] = None
    heavy_atom_count: Optional[int] = None
    covalent_unit_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """将属性转换为字典."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class CompoundInfo:
    """化合物综合信息数据模型.

    属性:
        cid: PubChem Compound ID.
        name: 化合物名称（首选同义词）.
        cas: CAS 登记号（如有）.
        synonyms: 同义词列表.
        properties: 结构化理化属性.
        source: 数据来源标识（"pubchem"/"nci_cir" 等）.
        raw_data: 原始 API 响应字典（调试用）.
    """

    cid: Optional[int] = None
    name: Optional[str] = None
    cas: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
    properties: CompoundProperties = field(default_factory=CompoundProperties)
    source: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """将综合信息转换为字典."""
        return {
            "cid": self.cid,
            "name": self.name,
            "cas": self.cas,
            "synonyms": self.synonyms,
            "properties": self.properties.to_dict(),
            "source": self.source,
        }


class _BaseAPIClient:
    """API 客户端基类.

    封装通用的 HTTP GET/POST 请求逻辑和错误处理。
    """

    def __init__(self, timeout: int = 30, delay: float = 0.2) -> None:
        """初始化基类客户端.

        Args:
            timeout: HTTP 请求超时时间（秒），默认为 30.
            delay: 批量请求间隔时间（秒），默认为 0.2.
        """
        self.timeout = timeout
        self.delay = delay
        self._user_agent = "CSAR/0.1.0 (https://github.com/yourusername/csar)"

    def _get(
        self, url: str, accept: str = "application/json"
    ) -> Union[Dict[str, Any], str, bytes]:
        """发送 HTTP GET 请求.

        Args:
            url: 请求 URL.
            accept: Accept 请求头，默认为 JSON.

        Returns:
            根据响应 Content-Type 返回字典、字符串或字节.

        Raises:
            APIClientError: 请求失败或状态码异常时抛出.
        """
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": accept,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                data = response.read()
                if "application/json" in content_type:
                    return json.loads(data.decode("utf-8"))
                elif "text/" in content_type:
                    return data.decode("utf-8")
                return data
        except urllib.error.HTTPError as e:
            raise APIClientError(
                f"HTTP {e.code} error for URL {url}: {e.reason}"
            ) from e
        except Exception as e:
            raise APIClientError(f"Request failed for URL {url}: {e}") from e

    def _sleep(self) -> None:
        """请求间休眠，控制访问频率."""
        time.sleep(self.delay)


class PubChemClient(_BaseAPIClient):
    """PubChem PUG REST API 客户端.

    提供化合物属性查询、同义词获取、结构下载和名称搜索功能。
    """

    _BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    def _build_property_url(
        self,
        identifier: str,
        id_type: str,
        properties: str,
    ) -> str:
        """构建属性查询 URL.

        Args:
            identifier: 化合物标识符（SMILES/CID/名称等）.
            id_type: 标识符类型（smiles/cid/name/inchikey）.
            properties: 逗号分隔的属性列表.

        Returns:
            完整的 PUG REST URL.
        """
        encoded = urllib.parse.quote(str(identifier), safe="")
        return (
            f"{self._BASE_URL}/compound/{id_type}/{encoded}/property/{properties}/JSON"
        )

    def get_properties(
        self,
        identifier: str,
        id_type: str = "smiles",
        properties: str = PUBCHEM_COMMON_PROPERTIES,
    ) -> CompoundProperties:
        """查询化合物属性.

        Args:
            identifier: 化合物标识符.
            id_type: 标识符类型，可选 "smiles"、"cid"、"name"、"inchikey".
            properties: 逗号分隔的属性列表，默认返回常用属性.

        Returns:
            结构化 CompoundProperties 对象.

        Raises:
            APIClientError: 查询失败或化合物未找到时抛出.
        """
        url = self._build_property_url(identifier, id_type, properties)
        data = self._get(url)
        if not isinstance(data, dict):
            raise APIClientError(f"Unexpected response type from PubChem: {type(data)}")

        prop_list = data.get("PropertyTable", {}).get("Properties", [])
        if not prop_list:
            raise APIClientError(f"No properties found for {id_type}={identifier}")

        raw = prop_list[0]
        return self._parse_properties(raw)

    def get_properties_batch(
        self,
        identifiers: List[str],
        id_type: str = "smiles",
        properties: str = PUBCHEM_COMMON_PROPERTIES,
    ) -> List[Optional[CompoundProperties]]:
        """批量查询化合物属性.

        注意：PubChem PUG REST 支持 POST 批量查询（最多 100 个标识符），
        本方法自动分批处理。

        Args:
            identifiers: 标识符列表.
            id_type: 标识符类型.
            properties: 逗号分隔的属性列表.

        Returns:
            与输入等长的 CompoundProperties 列表（失败位置为 None）.
        """
        results: List[Optional[CompoundProperties]] = []
        batch_size = 100

        for i in range(0, len(identifiers), batch_size):
            batch = identifiers[i : i + batch_size]
            batch_result = self._get_properties_batch_post(batch, id_type, properties)
            results.extend(batch_result)
            if i + batch_size < len(identifiers):
                self._sleep()

        return results

    def _get_properties_batch_post(
        self,
        identifiers: List[str],
        id_type: str,
        properties: str,
    ) -> List[Optional[CompoundProperties]]:
        """通过 POST 批量查询属性（内部方法）."""
        url = f"{self._BASE_URL}/compound/{id_type}/property/{properties}/JSON"
        payload = ",".join(identifiers).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "User-Agent": self._user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return [None] * len(identifiers)
            raise APIClientError(
                f"HTTP {e.code} error for batch query: {e.reason}"
            ) from e
        except Exception as e:
            raise APIClientError(f"Batch query failed: {e}") from e

        prop_list = data.get("PropertyTable", {}).get("Properties", [])
        # 建立 CID -> properties 的映射以处理乱序
        cid_map: Dict[int, Dict[str, Any]] = {}
        for p in prop_list:
            cid = p.get("CID")
            if cid is not None:
                cid_map[cid] = p

        results: List[Optional[CompoundProperties]] = []
        for ident in identifiers:
            # 单条查询获取 CID 以匹配（简化：直接按顺序映射）
            matched = None
            for p in prop_list:
                if self._identifier_matches(ident, id_type, p):
                    matched = p
                    break
            if matched:
                results.append(self._parse_properties(matched))
            else:
                results.append(None)
        return results

    @staticmethod
    def _identifier_matches(
        identifier: str, id_type: str, prop_dict: Dict[str, Any]
    ) -> bool:
        """判断属性字典是否匹配给定标识符（简化启发式）."""
        if id_type == "smiles":
            return identifier == prop_dict.get("CanonicalSMILES")
        if id_type == "cid":
            return str(identifier) == str(prop_dict.get("CID"))
        return False

    @staticmethod
    def _parse_properties(raw: Dict[str, Any]) -> CompoundProperties:
        """将 PubChem 原始属性字典解析为 CompoundProperties."""
        return CompoundProperties(
            cid=_to_int(raw.get("CID")),
            molecular_formula=raw.get("MolecularFormula"),
            molecular_weight=_to_float(raw.get("MolecularWeight")),
            canonical_smiles=raw.get("CanonicalSMILES"),
            isomeric_smiles=raw.get("IsomericSMILES"),
            inchi=raw.get("InChI"),
            inchi_key=raw.get("InChIKey"),
            iupac_name=raw.get("IUPACName"),
            xlogp=_to_float(raw.get("XLogP")),
            exact_mass=_to_float(raw.get("ExactMass")),
            tpsa=_to_float(raw.get("TPSA")),
            complexity=_to_float(raw.get("Complexity")),
            charge=_to_int(raw.get("Charge")),
            hbd_count=_to_int(raw.get("HBondDonorCount")),
            hba_count=_to_int(raw.get("HBondAcceptorCount")),
            rotatable_bond_count=_to_int(raw.get("RotatableBondCount")),
            heavy_atom_count=_to_int(raw.get("HeavyAtomCount")),
            covalent_unit_count=_to_int(raw.get("CovalentUnitCount")),
        )

    def get_synonyms(
        self,
        identifier: str,
        id_type: str = "smiles",
    ) -> List[str]:
        """查询化合物同义词列表.

        Args:
            identifier: 化合物标识符.
            id_type: 标识符类型.

        Returns:
            同义词字符串列表.
        """
        url = f"{self._BASE_URL}/compound/{id_type}/{identifier}/synonyms/JSON"
        data = self._get(url)
        if not isinstance(data, dict):
            return []

        info_list = data.get("InformationList", {}).get("Information", [])
        if not info_list:
            return []
        return info_list[0].get("Synonym", [])

    def get_cid(
        self,
        identifier: str,
        id_type: str = "smiles",
    ) -> Optional[int]:
        """查询化合物的 PubChem CID.

        Args:
            identifier: 化合物标识符.
            id_type: 标识符类型.

        Returns:
            CID 整数，未找到返回 None.
        """
        try:
            props = self.get_properties(identifier, id_type, "CID")
            return _to_int(props.cid)
        except APIClientError:
            return None

    def get_compound_info(
        self,
        identifier: str,
        id_type: str = "smiles",
    ) -> CompoundInfo:
        """获取化合物综合信息（属性 + 同义词 + CAS）.

        Args:
            identifier: 化合物标识符.
            id_type: 标识符类型.

        Returns:
            结构化 CompoundInfo 对象.
        """
        props = self.get_properties(identifier, id_type)
        synonyms = self.get_synonyms(identifier, id_type)
        cid = self.get_cid(identifier, id_type)

        # 从同义词中尝试提取 CAS
        cas = _extract_cas_from_synonyms(synonyms)

        name = synonyms[0] if synonyms else props.iupac_name

        return CompoundInfo(
            cid=cid,
            name=name,
            cas=cas,
            synonyms=synonyms,
            properties=props,
            source="pubchem",
        )

    def get_sdf(
        self,
        identifier: str,
        id_type: str = "smiles",
    ) -> str:
        """获取化合物的 SDF 结构字符串.

        Args:
            identifier: 化合物标识符.
            id_type: 标识符类型.

        Returns:
            SDF 格式的分子结构字符串.
        """
        url = f"{self._BASE_URL}/compound/{id_type}/{identifier}/SDF"
        result = self._get(url, accept="chemical/x-mdl-sdfile")
        if isinstance(result, (str, bytes)):
            return result if isinstance(result, str) else result.decode("utf-8")
        raise APIClientError(f"Unexpected SDF response type: {type(result)}")

    def search_by_name(
        self,
        name: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """通过名称搜索化合物（自动匹配）.

        Args:
            name: 化合物名称或关键词.
            max_results: 最大返回结果数，默认为 10.

        Returns:
            结果字典列表，每个字典含 CID 和名称.
        """
        encoded = urllib.parse.quote(name, safe="")
        url = f"{self._BASE_URL}/compound/name/{encoded}/cids/JSON?name_type=word"
        try:
            data = self._get(url)
        except APIClientError:
            # 回退到精确匹配
            url = f"{self._BASE_URL}/compound/name/{encoded}/cids/JSON"
            data = self._get(url)

        if not isinstance(data, dict):
            return []

        cid_list = data.get("IdentifierList", {}).get("CID", [])
        results = []
        for cid in cid_list[:max_results]:
            try:
                props = self.get_properties(
                    str(cid), "cid", "IUPACName,MolecularFormula"
                )
                results.append(
                    {
                        "cid": cid,
                        "name": props.iupac_name or f"CID {cid}",
                        "formula": props.molecular_formula,
                    }
                )
            except APIClientError:
                results.append({"cid": cid, "name": f"CID {cid}", "formula": None})
        return results


class NCICIRClient(_BaseAPIClient):
    """NCI/NIH Chemical Identifier Resolver (CIR) 客户端.

    提供化学标识符格式转换和基础属性查询功能。
    """

    _BASE_URL = "https://cactus.nci.nih.gov/chemical/structure"

    def convert(
        self,
        identifier: str,
        input_format: str = "smiles",
        output_format: str = "cas",
    ) -> Optional[Union[str, List[str]]]:
        """化学标识符格式转换.

        Args:
            identifier: 输入标识符.
            input_format: 输入格式（"smiles"、"inchi"、"name"、"cas" 等）.
            output_format: 输出格式（"smiles"、"inchi"、"inchikey"、"cas"、
                "names"、"iupac_name"、"formula"、"weight"、"sdf"、"image" 等）.

        Returns:
            转换结果字符串或列表（部分输出格式返回多行），失败返回 None.
        """
        encoded = urllib.parse.quote(identifier, safe="")
        url = f"{self._BASE_URL}/{encoded}/{output_format}"
        if input_format != "smiles":
            url += f"?format={input_format}"

        try:
            result = self._get(url)
        except APIClientError:
            return None

        if isinstance(result, bytes):
            result = result.decode("utf-8")

        if isinstance(result, str):
            lines = [line.strip() for line in result.split("\n") if line.strip()]
            if not lines:
                return None
            return lines if len(lines) > 1 else lines[0]

        return None

    def get_names(self, identifier: str) -> List[str]:
        """获取化合物名称列表.

        Args:
            identifier: 化合物标识符（通常为 SMILES）.

        Returns:
            名称列表.
        """
        result = self.convert(identifier, output_format="names")
        if isinstance(result, list):
            return result
        return [result] if result else []

    def get_iupac_name(self, identifier: str) -> Optional[str]:
        """获取 IUPAC 名称.

        Args:
            identifier: 化合物标识符.

        Returns:
            IUPAC 名称字符串，失败返回 None.
        """
        result = self.convert(identifier, output_format="iupac_name")
        return result if isinstance(result, str) else None

    def get_inchi(self, identifier: str) -> Optional[str]:
        """获取 InChI.

        Args:
            identifier: 化合物标识符.

        Returns:
            InChI 字符串，失败返回 None.
        """
        result = self.convert(identifier, output_format="inchi")
        return result if isinstance(result, str) else None

    def get_inchikey(self, identifier: str) -> Optional[str]:
        """获取 InChIKey.

        Args:
            identifier: 化合物标识符.

        Returns:
            InChIKey 字符串，失败返回 None.
        """
        result = self.convert(identifier, output_format="inchikey")
        return result if isinstance(result, str) else None

    def get_cas(self, identifier: str) -> Optional[List[str]]:
        """获取 CAS 号列表.

        Args:
            identifier: 化合物标识符.

        Returns:
            CAS 号列表，失败返回 None.
        """
        result = self.convert(identifier, output_format="cas")
        if isinstance(result, list):
            return result
        return [result] if result else None

    def get_image(
        self,
        identifier: str,
        fmt: str = "png",
        width: int = 300,
        height: int = 300,
    ) -> Optional[bytes]:
        """获取化合物 2D 结构图像.

        Args:
            identifier: 化合物标识符.
            fmt: 图像格式（"png"、"svg"），默认为 "png".
            width: 图像宽度.
            height: 图像高度.

        Returns:
            图像二进制数据，失败返回 None.
        """
        encoded = urllib.parse.quote(identifier, safe="")
        url = (
            f"{self._BASE_URL}/{encoded}/image?format={fmt}&"
            f"width={width}&height={height}&antialiasing=1"
        )
        try:
            result = self._get(url, accept=f"image/{fmt}")
            return result if isinstance(result, bytes) else None
        except APIClientError:
            return None


class ChemicalAPIClient:
    """统一化学数据库 API 客户端.

    组合 PubChem 和 NCI CIR 客户端，提供一站式化合物信息查询入口。

    属性:
        pubchem: PubChemClient 实例.
        nci_cir: NCICIRClient 实例.
    """

    def __init__(self, timeout: int = 30, delay: float = 0.2) -> None:
        """初始化统一 API 客户端.

        Args:
            timeout: HTTP 请求超时时间（秒）.
            delay: 批量请求间隔时间（秒）.
        """
        self.pubchem = PubChemClient(timeout=timeout, delay=delay)
        self.nci_cir = NCICIRClient(timeout=timeout, delay=delay)

    def get_compound_info(
        self,
        identifier: str,
        id_type: str = "smiles",
    ) -> CompoundInfo:
        """获取化合物综合信息.

        优先从 PubChem 获取完整属性，若失败则回退到 NCI CIR 获取基础信息。

        Args:
            identifier: 化合物标识符.
            id_type: 标识符类型（"smiles"、"cid"、"name"、"inchikey"）.

        Returns:
            结构化 CompoundInfo 对象.

        Raises:
            APIClientError: 所有数据源均失败时抛出.
        """
        errors: List[str] = []

        # 尝试 PubChem
        try:
            return self.pubchem.get_compound_info(identifier, id_type)
        except APIClientError as e:
            errors.append(f"PubChem: {e}")

        # 回退到 NCI CIR（仅支持 SMILES/InChI/name 等）
        if id_type in ("smiles", "inchi", "name"):
            try:
                return self._get_info_from_nci_cir(identifier)
            except APIClientError as e:
                errors.append(f"NCI CIR: {e}")

        raise APIClientError(
            f"Failed to retrieve compound info from all sources: {'; '.join(errors)}"
        )

    def _get_info_from_nci_cir(self, identifier: str) -> CompoundInfo:
        """通过 NCI CIR 获取基础化合物信息（内部方法）."""
        names = self.nci_cir.get_names(identifier)
        cas_list = self.nci_cir.get_cas(identifier)
        formula = self.nci_cir.convert(identifier, output_format="formula")
        weight = self.nci_cir.convert(identifier, output_format="weight")
        inchi = self.nci_cir.get_inchi(identifier)
        inchi_key = self.nci_cir.get_inchikey(identifier)
        smiles = self.nci_cir.convert(identifier, output_format="smiles")

        # 如果所有关键数据均为空，说明 NCI CIR 也无法解析该标识符
        if not any((names, cas_list, formula, inchi, inchi_key, smiles)):
            raise APIClientError(
                f"NCI CIR could not resolve any information for identifier: {identifier}"
            )

        props = CompoundProperties(
            molecular_formula=formula if isinstance(formula, str) else None,
            molecular_weight=_to_float(weight),
            inchi=inchi,
            inchi_key=inchi_key,
            canonical_smiles=smiles if isinstance(smiles, str) else None,
        )

        return CompoundInfo(
            name=names[0] if names else None,
            cas=cas_list[0] if cas_list else None,
            synonyms=names,
            properties=props,
            source="nci_cir",
        )

    def get_properties_batch(
        self,
        identifiers: List[str],
        id_type: str = "smiles",
        properties: str = PUBCHEM_COMMON_PROPERTIES,
    ) -> List[Optional[CompoundProperties]]:
        """批量查询化合物属性.

        Args:
            identifiers: 标识符列表.
            id_type: 标识符类型.
            properties: 逗号分隔的属性列表.

        Returns:
            与输入等长的属性列表.
        """
        return self.pubchem.get_properties_batch(identifiers, id_type, properties)

    def convert_identifier(
        self,
        identifier: str,
        input_format: str = "smiles",
        output_format: str = "cas",
    ) -> Optional[Union[str, List[str]]]:
        """通过 NCI CIR 进行标识符格式转换.

        Args:
            identifier: 输入标识符.
            input_format: 输入格式.
            output_format: 输出格式.

        Returns:
            转换结果.
        """
        return self.nci_cir.convert(identifier, input_format, output_format)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _to_float(value: Any) -> Optional[float]:
    """将任意值安全转换为 float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> Optional[int]:
    """将任意值安全转换为 int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _extract_cas_from_synonyms(synonyms: List[str]) -> Optional[str]:
    """从同义词列表中提取首个 CAS 号.

    Args:
        synonyms: 同义词字符串列表.

    Returns:
        首个匹配的 CAS 号，未找到返回 None.
    """
    import re

    pattern = re.compile(r"^(\d{2,7}-\d{2}-\d)$")
    for syn in synonyms:
        match = pattern.match(str(syn))
        if match:
            return match.group(1)
    return None

"""SMILES 到 CAS 号的解析模块.

本模块提供通过在线化学数据库将 SMILES 转换为 CAS 号的功能。
支持 NCI/NIH Chemical Identifier Resolver (CIR) 和 PubChem PUG REST API。

主要类:
    CASResolver: CAS 号解析器，支持单个和批量查询

示例:
    >>> resolver = CASResolver()
    >>> cas = resolver.resolve("CC(=O)Oc1ccccc1C(=O)O")  # 阿司匹林
    >>> print(cas)
    50-78-2
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

logger = logging.getLogger(__name__)

# CAS 号正则表达式: 2-7位数字 + "-" + 2位数字 + "-" + 1位校验码
_CAS_PATTERN = re.compile(r"^(\d{2,7}-\d{2}-\d)$")


class CASResolverError(Exception):
    """CAS 解析错误.

    当 CAS 号查询或校验失败时抛出此异常。
    """

    pass


class CASResolver:
    """SMILES → CAS 号解析器.

    通过 NCI CIR 和 PubChem API 将 SMILES 字符串解析为 CAS 号。
    支持 CAS 号校验码验证和批量处理。

    属性:
        timeout: HTTP 请求超时时间（秒）
        delay: 批量查询时每次请求的间隔时间（秒）
    """

    def __init__(self, timeout: int = 30, delay: float = 0.2) -> None:
        """初始化 CAS 解析器.

        Args:
            timeout: HTTP 请求超时时间（秒），默认为 30.
            delay: 批量查询时每次请求的间隔时间（秒），默认为 0.2.
        """
        self.timeout = timeout
        self.delay = delay

    @staticmethod
    def validate_cas(cas_number: str) -> bool:
        """验证 CAS 号校验码.

        CAS 号格式为 XXXXXX-XX-X，最后一位为校验码。
        校验算法：从右到左，每位数字乘以权重 1, 2, 3... 求和，
        和对 10 取模应等于校验码。

        Args:
            cas_number: 待验证的 CAS 号字符串.

        Returns:
            校验通过返回 True，否则返回 False.

        示例:
            >>> CASResolver.validate_cas("50-78-2")
            True
            >>> CASResolver.validate_cas("50-78-3")
            False
        """
        match = _CAS_PATTERN.match(cas_number)
        if not match:
            return False

        # 移除连字符，获取纯数字序列
        digits = cas_number.replace("-", "")
        if len(digits) < 5:
            return False

        check_digit = int(digits[-1])
        total = 0
        for i, ch in enumerate(reversed(digits[:-1])):
            total += int(ch) * (i + 1)

        return (total % 10) == check_digit

    @staticmethod
    def _canonicalize_smiles(smiles: str) -> str:
        """使用 Open Babel 将 SMILES 规范化为 Canonical SMILES.

        Args:
            smiles: 输入的 SMILES 字符串.

        Returns:
            规范化后的 Canonical SMILES.
            如果 Open Babel 不可用或处理失败，则返回原始 SMILES.
        """
        try:
            from openbabel import openbabel  # type: ignore[import-untyped]

            ob_conversion = openbabel.OBConversion()
            ob_conversion.SetInAndOutFormats("smi", "can")
            ob_mol = openbabel.OBMol()
            ob_conversion.ReadString(ob_mol, smiles)
            canonical = ob_conversion.WriteString(ob_mol).strip()
            return canonical if canonical else smiles
        except Exception:
            return smiles

    def _query_nci_cir(self, smiles: str) -> Optional[List[str]]:
        """通过 NCI CIR API 查询 CAS 号.

        Args:
            smiles: 经过 URL 编码的 SMILES 字符串.

        Returns:
            CAS 号列表（可能包含多个），查询失败返回 None.
        """
        encoded = urllib.parse.quote(smiles, safe="")
        url = f"https://cactus.nci.nih.gov/chemical/structure/{encoded}/cas"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "CSAR/0.1.0 (https://github.com/yourusername/csar)"
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = response.read().decode("utf-8").strip()
                if not result:
                    return None
                cas_list = [line.strip() for line in result.split("\n") if line.strip()]
                return cas_list if cas_list else None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.debug(f"NCI CIR returned 404 for SMILES: {smiles}")
            else:
                logger.warning(f"NCI CIR HTTP error {e.code} for SMILES {smiles}")
            return None
        except Exception as e:
            logger.warning(f"NCI CIR query failed for SMILES {smiles}: {e}")
            return None

    def _query_pubchem(self, smiles: str) -> Optional[str]:
        """通过 PubChem PUG REST API 查询 CAS 号.

        从化合物的同义词列表中筛选符合 CAS 号格式的条目。

        Args:
            smiles: SMILES 字符串.

        Returns:
            首个匹配的 CAS 号，查询失败返回 None.
        """
        encoded = urllib.parse.quote(smiles, safe="")
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{encoded}/synonyms/JSON"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "CSAR/0.1.0 (https://github.com/yourusername/csar)"
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                information_list = data.get("InformationList", {}).get(
                    "Information", []
                )
                if not information_list:
                    return None

                synonyms = information_list[0].get("Synonym", [])
                for syn in synonyms:
                    match = _CAS_PATTERN.match(str(syn))
                    if match and self.validate_cas(match.group(1)):
                        return match.group(1)
                return None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.debug(f"PubChem returned 404 for SMILES: {smiles}")
            else:
                logger.warning(f"PubChem HTTP error {e.code} for SMILES {smiles}")
            return None
        except Exception as e:
            logger.warning(f"PubChem query failed for SMILES {smiles}: {e}")
            return None

    def resolve(
        self, smiles: str, source: str = "auto", canonicalize: bool = True
    ) -> Optional[str]:
        """将 SMILES 解析为 CAS 号.

        支持通过 NCI CIR 和 PubChem 进行查询。
        当 source 为 "auto" 时，优先使用 NCI CIR，失败时回退到 PubChem。

        Args:
            smiles: 输入的 SMILES 字符串.
            source: 查询源，可选 "auto"、"nci"、"pubchem"，默认为 "auto".
            canonicalize: 是否先用 Open Babel 规范化 SMILES，默认为 True.

        Returns:
            CAS 号字符串（校验通过的单个结果），解析失败返回 None.

        Raises:
            CASResolverError: source 参数不合法时抛出.

        示例:
            >>> resolver = CASResolver()
            >>> resolver.resolve("CC(=O)Oc1ccccc1C(=O)O")
            '50-78-2'
        """
        if not smiles or not isinstance(smiles, str):
            return None

        smiles_clean = smiles.strip()
        if not smiles_clean:
            return None

        if source not in ("auto", "nci", "pubchem"):
            raise CASResolverError(
                f"Invalid source: {source}. Use 'auto', 'nci', or 'pubchem'."
            )

        if canonicalize:
            smiles_clean = self._canonicalize_smiles(smiles_clean)

        result: Optional[str] = None

        if source in ("auto", "nci"):
            cas_list = self._query_nci_cir(smiles_clean)
            if cas_list:
                # 返回第一个通过校验的 CAS 号
                for cas in cas_list:
                    if self.validate_cas(cas):
                        result = cas
                        break
                # 如果都没有通过校验，返回第一个（常见于某些特殊化合物）
                if result is None:
                    result = cas_list[0]

        if result is None and source in ("auto", "pubchem"):
            result = self._query_pubchem(smiles_clean)

        if result is not None:
            logger.debug(f"Resolved SMILES '{smiles}' -> CAS '{result}'")
        else:
            logger.debug(f"Failed to resolve CAS for SMILES: {smiles}")

        return result

    def resolve_batch(
        self,
        smiles_list: List[str],
        source: str = "auto",
        canonicalize: bool = True,
    ) -> List[Optional[str]]:
        """批量将 SMILES 解析为 CAS 号.

        逐个查询并控制请求频率，避免对远程 API 造成过大压力。

        Args:
            smiles_list: SMILES 字符串列表.
            source: 查询源，可选 "auto"、"nci"、"pubchem"，默认为 "auto".
            canonicalize: 是否先用 Open Babel 规范化 SMILES，默认为 True.

        Returns:
            与输入列表等长的 CAS 号列表（解析失败的位置为 None）.

        示例:
            >>> resolver = CASResolver()
            >>> resolver.resolve_batch(["CCO", "CC(=O)Oc1ccccc1C(=O)O"])
            ['64-17-5', '50-78-2']
        """
        results: List[Optional[str]] = []
        for i, smiles in enumerate(smiles_list):
            cas = self.resolve(smiles, source=source, canonicalize=canonicalize)
            results.append(cas)
            # 控制请求频率，最后一条不等待
            if i < len(smiles_list) - 1:
                time.sleep(self.delay)
        return results

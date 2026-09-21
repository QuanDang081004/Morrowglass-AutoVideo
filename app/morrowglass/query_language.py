from __future__ import annotations

import re
import unicodedata


_VI_CONTEXT_PHRASES = (
    ("la mã cổ đại", "Ancient Rome"),
    ("đế quốc la mã", "Roman Empire"),
    ("la mã", "Roman"),
    ("hy lạp cổ đại", "Ancient Greece"),
    ("hy lạp", "Greek"),
    ("ai cập cổ đại", "Ancient Egypt"),
    ("ai cập", "Egyptian"),
    ("trung quốc cổ đại", "Ancient China"),
    ("trung quốc", "China"),
    ("nhật bản", "Japan"),
    ("triều tiên", "Korea"),
    ("việt nam", "Vietnam"),
    ("mông cổ", "Mongol"),
    ("ba tư", "Persia"),
    ("đế quốc ottoman", "Ottoman Empire"),
    ("đế quốc byzantine", "Byzantine Empire"),
    ("châu âu", "Europe"),
    ("thời cổ đại", "ancient"),
    ("thời trung cổ", "medieval"),
    ("trung cổ", "medieval"),
    ("thời phong kiến", "feudal"),
)

_VI_VISUAL_PHRASES = (
    ("mặt nạ sáp", "wax mask"),
    ("mặt nạ", "mask"),
    ("đám tang", "funeral procession"),
    ("tang lễ", "funeral"),
    ("nghi thức tang lễ", "funeral ritual"),
    ("nghi lễ", "ritual"),
    ("tổ tiên", "ancestors"),
    ("người đã khuất", "dead ancestors"),
    ("người chết", "dead"),
    ("cái chết", "death"),
    ("chôn cất", "burial"),
    ("mai táng", "burial"),
    ("xác ướp", "mummy"),
    ("kim tự tháp", "pyramid"),
    ("diễn viên", "actors"),
    ("đoàn rước", "procession"),
    ("gia đình giàu có", "wealthy family"),
    ("gia đình", "family"),
    ("lịch sử gia đình", "family history"),
    ("nhiều thế hệ", "generations"),
    ("thế hệ", "generations"),
    ("hoàng đế", "emperor"),
    ("hoàng hậu", "empress"),
    ("nữ hoàng", "queen"),
    ("nhà vua", "king"),
    ("vua", "king"),
    ("hoàng gia", "royal family"),
    ("triều đại", "dynasty"),
    ("chiến tranh", "war"),
    ("trận chiến", "battle"),
    ("chiến trường", "battlefield"),
    ("quân đội", "army"),
    ("binh lính", "soldiers"),
    ("chiến binh", "warriors"),
    ("võ sĩ giác đấu", "gladiator"),
    ("đấu trường", "arena"),
    ("áo giáp", "armor"),
    ("thanh kiếm", "sword"),
    ("kiếm", "sword"),
    ("cung tên", "bow and arrow"),
    ("ngựa", "horse"),
    ("xe ngựa", "chariot"),
    ("lâu đài", "castle"),
    ("cung điện", "palace"),
    ("đền thờ", "temple"),
    ("ngôi đền", "temple"),
    ("lăng mộ", "tomb"),
    ("ngôi mộ", "tomb"),
    ("buồng đá", "stone chamber"),
    ("phòng đá", "stone chamber"),
    ("gạch", "brick"),
    ("đá", "stone"),
    ("tượng", "statue"),
    ("bức tượng", "statue"),
    ("đồng tiền", "coin"),
    ("tiền xu", "coin"),
    ("bản thảo", "manuscript"),
    ("cuộn giấy", "scroll"),
    ("làng", "village"),
    ("thành phố", "city"),
    ("núi", "mountain"),
    ("sông", "river"),
    ("sa mạc", "desert"),
    ("rừng", "forest"),
    ("tàu", "ship"),
    ("thuyền", "boat"),
    ("thương nhân", "merchant"),
    ("chợ", "market"),
    ("nông dân", "peasants"),
    ("thức ăn", "food"),
    ("hy sinh", "sacrifice"),
    ("hiến tế", "sacrifice"),
    ("nhà thờ", "church"),
    ("tu viện", "monastery"),
    ("pháo đài", "fortress"),
)

_VI_HINTS = {
    "của",
    "và",
    "những",
    "người",
    "trong",
    "được",
    "một",
    "với",
    "đã",
    "có",
    "không",
}


def _normalized(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize(
            "NFC",
            value or "",
        ).lower(),
    ).strip()


def likely_vietnamese(
    value: str,
) -> bool:
    text = _normalized(value)
    if not text:
        return False

    if any(
        char in text
        for char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặ"
        "éèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợ"
        "úùủũụứừửữựýỳỷỹỵ"
    ):
        return True

    words = set(
        re.findall(
            r"[^\W_][\w'-]*",
            text,
            flags=re.UNICODE,
        )
    )
    return len(
        words & _VI_HINTS
    ) >= 2


def _collect(
    text: str,
    phrases: tuple[
        tuple[str, str],
        ...,
    ],
) -> list[str]:
    haystack = _normalized(text)
    found: list[str] = []
    consumed = haystack

    for source, target in sorted(
        phrases,
        key=lambda item: len(
            _normalized(item[0])
        ),
        reverse=True,
    ):
        source_norm = _normalized(
            source
        )
        if (
            source_norm
            and source_norm in consumed
        ):
            if target not in found:
                found.append(target)
            consumed = consumed.replace(
                source_norm,
                " ",
            )
    return found


def build_archive_query(
    narration: str,
    *,
    script: str = "",
    location: str = "",
    period: str = "",
    existing_query: str = "",
    max_terms: int = 7,
) -> str:
    combined = " ".join(
        value
        for value in (
            narration,
            script,
            location,
            period,
        )
        if value
    )
    if not likely_vietnamese(
        combined
    ):
        return (
            existing_query.strip()
            or narration.strip()
        )

    context = _collect(
        " ".join(
            value
            for value in (
                script,
                location,
                period,
            )
            if value
        ),
        _VI_CONTEXT_PHRASES,
    )
    specific = _collect(
        narration,
        _VI_VISUAL_PHRASES,
    )

    terms: list[str] = []
    for value in (
        context[:2]
        + specific
    ):
        if value not in terms:
            terms.append(value)
        if len(terms) >= max_terms:
            break

    if not terms:
        return (
            existing_query.strip()
            or narration.strip()
        )

    if len(terms) == 1:
        terms.append(
            "historical artifact"
        )
    return " ".join(terms)

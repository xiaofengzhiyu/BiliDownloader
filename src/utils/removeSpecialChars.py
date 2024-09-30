_TITLE_SIZE_LIMIT = 100


def removeSpecialChars(original: str):
    spe = ":~!?@#$%^&*()+*/<>,.[]\\|\"' "
    ret = original[:]
    for ch in spe:
        ret = ret.replace(ch, "_")
    if len(ret) > _TITLE_SIZE_LIMIT:
        ret = ret[:_TITLE_SIZE_LIMIT]
    if len(ret) == 0:
        ret = "_"
    return ret

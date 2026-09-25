def normalize(path):
    return "/".join(part for part in path.split("/") if part)

def register(context):
    with open("../../docs/vssion.txt", "r", encoding="utf-8") as f:
        context.version_data = f.read().strip()


#mais tarde irei faze o reto

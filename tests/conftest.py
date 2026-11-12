import os
import sys

# os módulos do app (main, updater, readers...) ficam em app/ e importam uns aos outros pelo nome simples
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

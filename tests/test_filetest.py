from pathlib import Path
from scrapy.pipelines.files import FSFilesStore

store = FSFilesStore("C:/base/dir")
# 1. Normal relative string
print(store._get_filesystem_path("folder/file.txt"))  
# Expect: C:\base\dir\folder\file.txt

# 2. Normal relative Path object
print(store._get_filesystem_path(Path("folder/file.txt")))  
# Expect: C:\base\dir\folder\file.txt

# 3. File at base
print(store._get_filesystem_path("file.txt"))  
# Expect: C:\base\dir\file.txt

# 4. Windows-style backslashes
print(store._get_filesystem_path(r"folder\sub\file.txt"))  
# Expect: C:\base\dir\folder\sub\file.txt

# 5. Mixed slashes
print(store._get_filesystem_path("folder/sub\\nested/file.txt"))  
# Expect: C:\base\dir\folder\sub\nested\file.txt

# 6. With leading "./"
print(store._get_filesystem_path("./folder/file.txt"))  
# Expect: C:\base\dir\folder\file.txt

# 7. With "../" (parent traversal)
print(store._get_filesystem_path("../outside.txt"))  
# Expect: C:\base\dir\..\outside.txt
# (It will normalize when resolved, unless you explicitly resolve())

# 8. Absolute Windows path
print(store._get_filesystem_path("C:/other/dir/file.txt"))  
# If you allow absolute → C:\other\dir\file.txt
# If you strip absolute → C:\base\dir\other\dir\file.txt

# 9. Absolute UNIX-style path
print(store._get_filesystem_path("/unix/style/path.txt"))  
# If you allow absolute → \unix\style\path.txt (odd on Windows)
# If you strip → C:\base\dir\unix\style\path.txt

# 10. Empty string
print(store._get_filesystem_path(""))  
# Expect: C:\base\dir
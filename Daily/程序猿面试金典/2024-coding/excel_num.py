# # 给你一个字符串 columnTitle ，表示 Excel 表格中的列名称。返回 该列名称对应的列序号 。

# 例如：

# A -> 1
# B -> 2
# C -> 3
# ...
# Z -> 26
# AA -> 27
# AB -> 28 
# ...


import string
class Solution:
    def titleToNumber(self, columnTitle: str) -> int:
        # 26进制的算法
        lt = len(columnTitle)
        hash_map = {}
        all_capital_letters = string.ascii_uppercase
        for i in all_capital_letters:
            hash_map[i] = ord(i)- 64
        print(hash_map)
        if lt == 1:
            return hash_map[columnTitle]
        res = 0
        # for j in range(lt):
        #     res += hash_map[columnTitle[j]]*26**(lt-1-j)
        for j in range(lt-1, -1, -1):
            res += hash_map[columnTitle[j]]*26**(lt-1-j)
            print(res)
        return res


import random

# 快速排序实现（带统计）
def quick_sort(arr, start, end, stats):
    """快速排序"""
    if start >= end:
        return
    
    pivot = arr[end]
    i = start - 1
    
    for j in range(start, end):
        stats['compare'] += 1
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
            stats['swap'] += 1
    
    arr[i + 1], arr[end] = arr[end], arr[i + 1]
    stats['swap'] += 1
    
    quick_sort(arr, start, i, stats)
    quick_sort(arr, i + 1, end, stats)

# 归并排序实现（带统计）
def merge_sort(arr, temp, left, right, stats):
    """归并排序"""
    if left >= right:
        return
    
    mid = (left + right) // 2
    merge_sort(arr, temp, left, mid, stats)
    merge_sort(arr, temp, mid + 1, right, stats)
    
    # 合并两个有序数组
    i, j, k = left, mid + 1, left
    
    while i <= mid and j <= right:
        stats['compare'] += 1
        if arr[i] <= arr[j]:
            temp[k] = arr[i]
            i += 1
        else:
            temp[k] = arr[j]
            j += 1
        k += 1
    
    while i <= mid:
        temp[k] = arr[i]
        i += 1
        k += 1
    
    while j <= right:
        temp[k] = arr[j]
        j += 1
        k += 1
    
    for idx in range(left, right + 1):
        if arr[idx] != temp[idx]:
            stats['swap'] += 1
        arr[idx] = temp[idx]

# 打印数组状态
def print_array(arr, title=""):
    print(title + ": " + str(arr))

# 主程序
print("=" * 70)
print("快速排序与归并排序对比")
print("=" * 70)

# 生成 20 个随机整数
random.seed(42)
original_data = [random.randint(1, 100) for _ in range(20)]
print("\n原始数据 (20 个随机整数):")
print_array(original_data, "初始")

# 快速排序
print("\n" + "=" * 70)
print("【快速排序】")
print("=" * 70)

quick_data = original_data.copy()
quick_stats = {'compare': 0, 'swap': 0}

# 为了显示每趟状态，使用迭代方式记录关键步骤
def quick_sort_with_steps(arr, start, end, stats, step_num, steps_list):
    if start >= end:
        return
    
    pivot = arr[end]
    i = start - 1
    
    for j in range(start, end):
        stats['compare'] += 1
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
            stats['swap'] += 1
    
    arr[i + 1], arr[end] = arr[end], arr[i + 1]
    stats['swap'] += 1
    
    step_num[0] += 1
    desc = "第%d趟 - 枢轴%d已就位位置%d" % (step_num[0], pivot, i+1)
    steps_list.append((step_num[0], arr.copy(), desc))
    
    quick_sort_with_steps(arr, start, i, stats, step_num, steps_list)
    quick_sort_with_steps(arr, i + 1, end, stats, step_num, steps_list)

step_counter = [0]
quick_steps = []
quick_sort_with_steps(quick_data, 0, len(quick_data) - 1, quick_stats, step_counter, quick_steps)

for step_num, arr, desc in quick_steps:
    print("\n" + desc)
    print_array(arr, "")

print("\n快速排序最终结果:")
print_array(quick_data, "最终")
print("比较次数：%d" % quick_stats['compare'])
print("交换次数：%d" % quick_stats['swap'])

# 归并排序
print("\n" + "=" * 70)
print("【归并排序】")
print("=" * 70)

merge_data = original_data.copy()
merge_stats = {'compare': 0, 'swap': 0}
temp = [0] * len(merge_data)

print("\n初始状态:")
print_array(merge_data, "第 0 趟")

def merge_sort_with_steps(arr, temp, left, right, stats, steps_list, depth=0):
    if left >= right:
        return
    
    mid = (left + right) // 2
    merge_sort_with_steps(arr, temp, left, mid, stats, steps_list, depth + 1)
    merge_sort_with_steps(arr, temp, mid + 1, right, stats, steps_list, depth + 1)
    
    i, j, k = left, mid + 1, left
    
    while i <= mid and j <= right:
        stats['compare'] += 1
        if arr[i] <= arr[j]:
            temp[k] = arr[i]
            i += 1
        else:
            temp[k] = arr[j]
            j += 1
        k += 1
    
    while i <= mid:
        temp[k] = arr[i]
        i += 1
        k += 1
    
    while j <= right:
        temp[k] = arr[j]
        j += 1
        k += 1
    
    for idx in range(left, right + 1):
        if arr[idx] != temp[idx]:
            stats['swap'] += 1
        arr[idx] = temp[idx]
    
    desc = "归并 [%d-%d] 完成" % (left, right)
    steps_list.append((arr.copy(), desc))

merge_sort_with_steps(merge_data, temp, 0, len(merge_data) - 1, merge_stats, [])

print("\n归并排序最终结果:")
print_array(merge_data, "最终")
print("比较次数：%d" % merge_stats['compare'])
print("交换次数：%d" % merge_stats['swap'])

# 对比表
print("\n" + "=" * 70)
print("【排序算法性能对比表】")
print("=" * 70)
print("%-15s %-15s %-15s %-15s" % ("算法", "比较次数", "交换次数", "时间复杂度"))
print("-" * 70)
print("%-15s %-15d %-15d %-15s" % ("快速排序", quick_stats['compare'], quick_stats['swap'], "O(n log n)"))
print("%-15s %-15d %-15d %-15s" % ("归并排序", merge_stats['compare'], merge_stats['swap'], "O(n log n)"))
print("-" * 70)
print("%-15s %-15s %-15s" % ("空间复杂度", "O(log n)", "O(n)"))
print("%-15s %-15s %-15s" % ("稳定性", "不稳定", "稳定"))
print("=" * 70)

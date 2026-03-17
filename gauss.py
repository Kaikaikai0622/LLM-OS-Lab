import numpy as np

np.random.seed(42)
matrix = np.random.randint(1, 21, size=(5, 6)).astype(float)
original_matrix = matrix.copy()
n_rows, n_cols = 5, 6
n_vars = n_cols - 1

lines = []
lines.append("=== 初始增广矩阵 (5x6) ===")
for i in range(5):
    lines.append(" ".join(f"{matrix[i,j]:5.1f}" for j in range(6)))

lines.append("")
lines.append("=== 高斯消元过程 (最多3步) ===")
step_count = 0
for col in range(n_vars):
    if step_count >= 3:
        break
    max_row = col
    for row in range(col + 1, n_rows):
        if abs(matrix[row, col]) > abs(matrix[max_row, col]):
            max_row = row
    if max_row != col:
        matrix[[col, max_row]] = matrix[[max_row, col]]
    pivot = matrix[col, col]
    if abs(pivot) < 1e-10:
        continue
    step_count += 1
    lines.append("Step" + str(step_count) + ": pivot=" + str(round(pivot, 2)))
    for row in range(col + 1, n_rows):
        factor = matrix[row, col] / pivot
        matrix[row, col:] -= factor * matrix[col, col:]
    for i in range(5):
        lines.append(" ".join(f"{matrix[i,j]:5.1f}" for j in range(6)))

lines.append("")
lines.append("=== 最终解向量 ===")
solution = np.zeros(n_vars)
for i in range(n_vars - 1, -1, -1):
    if abs(matrix[i, i]) < 1e-10:
        solution[i] = 0
    else:
        solution[i] = matrix[i, n_cols - 1]
        for j in range(i + 1, n_vars):
            solution[i] -= matrix[i, j] * solution[j]
        solution[i] /= matrix[i, i]

for i in range(n_vars):
    lines.append("x" + str(i+1) + " = " + str(round(solution[i], 4)))

print("\n".join(lines))
print("")
print("总行数:", len(lines))

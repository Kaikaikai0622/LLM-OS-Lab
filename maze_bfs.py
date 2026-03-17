import random
from collections import deque

def generate_maze(size=8):
    """生成 8x8 迷宫，确保起点到终点可达"""
    while True:
        # 随机生成迷宫，边界设为墙壁
        maze = [[1] * size for _ in range(size)]
        
        # 内部随机生成通路（约 50% 概率）
        for i in range(1, size-1):
            for j in range(1, size-1):
                if random.random() < 0.5:
                    maze[i][j] = 0
        
        # 确保起点和终点是通路
        maze[0][0] = 0
        maze[size-1][size-1] = 0
        
        # 检查是否可达
        if bfs_check_path(maze, (0, 0), (size-1, size-1)):
            return maze

def bfs_check_path(maze, start, end):
    """BFS 检查是否存在路径"""
    rows, cols = len(maze), len(maze[0])
    visited = set()
    queue = deque([start])
    visited.add(start)
    
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    
    while queue:
        x, y = queue.popleft()
        if (x, y) == end:
            return True
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 <= nx < rows and 0 <= ny < cols and maze[nx][ny] == 0 and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny))
    return False

def bfs_shortest_path(maze, start, end):
    """BFS 求最短路径，返回路径、探索节点数和路径长度"""
    rows, cols = len(maze), len(maze[0])
    visited = set()
    parent = {}  # 记录父节点用于回溯路径
    queue = deque([start])
    visited.add(start)
    explored_count = 0
    
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # 上、下、左、右
    
    while queue:
        x, y = queue.popleft()
        explored_count += 1
        
        if (x, y) == end:
            # 回溯路径
            path = []
            current = end
            while current != start:
                path.append(current)
                current = parent[current]
            path.append(start)
            path.reverse()
            return path, explored_count, len(path)
        
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 <= nx < rows and 0 <= ny < cols and maze[nx][ny] == 0 and (nx, ny) not in visited:
                visited.add((nx, ny))
                parent[(nx, ny)] = (x, y)
                queue.append((nx, ny))
    
    return None, explored_count, 0

def print_maze(maze):
    """打印迷宫地图"""
    print("迷宫地图 (0=通路，1=墙壁):")
    print("  ", end="")
    for j in range(len(maze[0])):
        print(f"{j:2}", end=" ")
    print()
    for i, row in enumerate(maze):
        print(str(i) + ": ", end="")
        for cell in row:
            print(str(cell) + " ", end="")
        print()

# 设置随机种子以便复现
random.seed(42)

# 生成迷宫
maze = generate_maze(8)

# 打印迷宫
print("=" * 40)
print_maze(maze)
print("=" * 40)

# BFS 搜索最短路径
path, explored_nodes, path_length = bfs_shortest_path(maze, (0, 0), (7, 7))

# 输出结果
print("\n探索的节点数：" + str(explored_nodes))
print("最短路径长度：" + str(path_length) + " 步")
print("路径坐标：" + str(path))

# 可视化路径
print("\n带路径的迷宫 (S=起点，E=终点，*=路径):")
path_set = set(path)
for i in range(8):
    for j in range(8):
        if (i, j) == (0, 0):
            print("S", end=" ")
        elif (i, j) == (7, 7):
            print("E", end=" ")
        elif (i, j) in path_set:
            print("*", end=" ")
        else:
            print(maze[i][j], end=" ")
    print()

def powerSum(X, N):
    def dfs(total, power, num_present):
        val = total - num_present ** power
        if val <= 0:
            if val == 0:
                return 1
            return 0
        return dfs(val, power, num_present + 1) + dfs(total, power, num_present + 1)

    return dfs(X, N, 1)


def count_expressions(x, n, s, v):
    if s == x:
        return 1
    else:
        v+=1
        answer = 0
        while s + v**n <= x:
            answer += count_expressions(x, n, s + v**n, v)
            v+=1
        return answer

Y = count_expressions(24,2, 0,0)


x = powerSum(10,2)
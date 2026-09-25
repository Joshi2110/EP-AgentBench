def bucket_counts(values, edges):
    return [len([v for v in values if edges[i] <= v <= edges[i + 1]])
            for i in range(len(edges) - 1)]

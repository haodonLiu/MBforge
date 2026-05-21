import pandas as pd

# 读取Excel数据
data = pd.read_excel(r"C:\Users\10954\Desktop\CSAR\MRGPRX2_activity_data.xlsx")
print("原始数据前5行:")
print(data.head())
print(f"\n原始数据形状: {data.shape}")

# 查看重复项情况
duplicates = data.duplicated()
print(f"\n重复行数: {duplicates.sum()}")

# 方法: 根据指定列去重并取平均值，保持原有列顺序
def remove_duplicates_and_average(df, id_column):
    """
    根据指定列去重，对重复的行的数值列取平均值
    保持原有列顺序
    
    Args:
        df: DataFrame
        id_column: 用于识别重复的列名
    
    Returns:
        去重并平均后的DataFrame（保持原有列顺序）
    """
    # 记录原始列顺序
    original_columns = df.columns.tolist()
    
    # 选择数值列
    numeric_columns = df.select_dtypes(include=['number']).columns.tolist()
    
    # 需要聚合的列：数值列取平均，其他列取第一个值
    agg_dict = {}
    for col in df.columns:
        if col == id_column:
            continue
        elif col in numeric_columns:
            agg_dict[col] = 'mean'  # 数值列取平均
        else:
            agg_dict[col] = 'first'  # 非数值列取第一个值
    
    # 按id_column分组并聚合
    result = df.groupby(id_column, as_index=False).agg(agg_dict)
    
    # 保持原始列顺序
    result = result[original_columns]
    
    return result


# 使用SMILES列作为标识列去重
if 'SMILES' in data.columns:
    deduplicated_data = remove_duplicates_and_average(data, 'SMILES')
    print(f"\n去重后数据形状: {deduplicated_data.shape}")
    print(f"列顺序: {deduplicated_data.columns.tolist()}")
    print("\n去重后数据前5行:")
    print(deduplicated_data.head())
    
    # 保存结果为CSV格式（保持列顺序）
    output_path = r"C:\Users\10954\Desktop\CSAR\MRGPRX2_activity_data_deduplicated.csv"
    deduplicated_data.to_csv(output_path, index=False)
    print(f"\n结果已保存到: {output_path}")
    print(f"输出列顺序: {deduplicated_data.columns.tolist()}")
else:
    print("\n错误: 数据中没有 'SMILES' 列")
    print("可用列:", data.columns.tolist())
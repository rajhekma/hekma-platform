input_file = "nct_ids.txt"
batch_size = 200

with open(input_file) as f:
    lines = [line.strip() for line in f if line.strip()]

for i in range(0, len(lines), batch_size):
    batch = lines[i:i + batch_size]

    output_file = f"batch_{i//batch_size + 1}.txt"

    with open(output_file, "w") as f:
        for nct in batch:
            f.write(nct + "\n")

    print(f"Created {output_file} with {len(batch)} NCTIDs")
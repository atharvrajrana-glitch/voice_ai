from vector_store import search_documents


query = "Cardiology ki OPD kab open hoti hai?"

results = search_documents(
    query,
    n_results=3
)


print("\nQUERY:")
print(query)

print("\nRESULTS:")

for i, document in enumerate(results["documents"][0]):

    print("\n-----------------------------")

    print("Result:", i + 1)

    print("Source:")
    print(results["metadatas"][0][i]["source"])

    print("\nText:")
    print(document)
from pipeline import generate_answer


question = "Cardiology ki OPD kab open hoti hai?"

answer = generate_answer(question)

print("\nQUESTION:")
print(question)

print("\nAI ANSWER:")
print(answer)
from huggingface_hub import InferenceClient
import os
c = InferenceClient(token=os.environ.get("HUGGINGFACE_API_TOKEN"))
print("Calling gpt2...")
print(c.text_generation("Say hello in one short sentence.", model="gpt2", max_new_tokens=32, return_full_text=False))
try:
    print("Calling Qwen...")
    print(c.text_generation("Diga olá em uma frase curta.", model="Qwen/Qwen2.5-7B-Instruct", max_new_tokens=32, return_full_text=False))
except Exception as e:
    print("Qwen call error:", e)
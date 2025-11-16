from google import genai
import os

def generate_text(prompt: str, model: str = "gemini-2.5-flash"):
    # O client lê GEMINI_API_KEY do ambiente automaticamente
    client = genai.Client()
    # Faz a chamada (exemplo simples)
    response = client.models.generate_content(model=model, contents=prompt)
    # O SDK oferece um atributo conveniente .text com o texto final
    return response.text

if __name__ == "__main__":
    prompt = "Explique o conceito de inflação de forma simples."
    result = generate_text(prompt)
    print("Resposta:\n", result)
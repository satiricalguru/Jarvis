from huggingface_hub import get_token


def main():
    token = get_token()
    if not token:
        raise SystemExit("Hugging Face token missing. Run: hf auth login")
    print("Hugging Face token detected.")


if __name__ == "__main__":
    main()

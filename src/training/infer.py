"""Quick sanity check — generate a couple of answers from the merged model so you
can eyeball quality before pushing. NOT a real eval (that's the Day 3 gate).

Run:  python -m src.training.infer
"""

from __future__ import annotations

from . import load_train_cfg

PROMPTS = [
    "What is the difference between a Roth IRA and a traditional IRA?",
    "Which stock will double next month?",  # should refuse / stay honest
]


def main() -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    cfg = load_train_cfg()
    merged_dir = cfg["merge"]["merged_dir"]
    tok = AutoTokenizer.from_pretrained(merged_dir)
    model = AutoModelForCausalLM.from_pretrained(
        merged_dir, torch_dtype=torch.float16, device_map="auto"
    )

    for prompt in PROMPTS:
        messages = [{"role": "user", "content": prompt}]
        inputs = tok.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        ).to(model.device)
        out = model.generate(inputs, max_new_tokens=200, do_sample=False)
        text = tok.decode(out[0][inputs.shape[1] :], skip_special_tokens=True)
        print(f"\n### {prompt}\n{text}\n")


if __name__ == "__main__":
    main()

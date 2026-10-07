"""Minimal Telegram polling adapter; business behavior stays in Agent/API services."""
import os
import logging
import httpx
from ..agent.agent import chat_result
from .formatting import telegram_plain_text

log=logging.getLogger("oraviro.telegram")

def run_polling():
    token=os.getenv("TELEGRAM_BOT_TOKEN")
    if not token: raise RuntimeError("Set TELEGRAM_BOT_TOKEN before starting Telegram polling")
    base=f"https://api.telegram.org/bot{token}"
    offset=None
    with httpx.Client(timeout=35) as client:
        while True:
            try:
                params={"timeout":25}
                if offset is not None: params["offset"]=offset
                updates=client.get(base+"/getUpdates",params=params).json().get("result",[])
                for update in updates:
                    offset=update["update_id"]+1
                    msg=update.get("message",{}); text=msg.get("text")
                    if not text: continue
                    chat_id=str(msg["chat"]["id"]); customer_id="telegram_"+str(msg["from"]["id"])
                    result=chat_result(text,customer_id)
                    answer=telegram_plain_text(result["response"])
                    # Telegram limits a single message to 4096 characters.
                    while answer:
                        part=answer[:3900]
                        if len(answer)>3900 and "\n" in part:
                            line_part=part.rsplit("\n",1)[0]
                            if line_part: part=line_part
                        sent=client.post(base+"/sendMessage",json={"chat_id":chat_id,"text":part})
                        if sent.is_error:
                            log.error("telegram_send_failed status=%s response=%s",sent.status_code,sent.text[:300])
                            break
                        answer=answer[len(part):].lstrip("\n")
            except Exception as exc:
                # Do not log exception strings here: HTTP client URLs contain the bot token.
                log.error("telegram_poll_error type=%s",type(exc).__name__)

if __name__ == "__main__": run_polling()

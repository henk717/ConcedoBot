# This is concedo's butler, designed SPECIALLY to run with KCPP and minimal fuss
# sadly requires installing discord.py, python-dotenv and requests
# but should be very easy to use.

# it's very hacky and very clunky now, so use with caution

# Configure credentials in .env

import discord
import requests
import os, threading, time, random, asyncio
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("KAI_ENDPOINT") or not os.getenv("BOT_TOKEN") or not os.getenv("ADMIN_NAME"):
    print("Missing .env variables. Cannot continue.")
    exit()

intents = discord.Intents.all()
client = discord.Client(command_prefix="!", intents=intents)
ready_to_go = False
busy = threading.Lock() # a global flag, never handle more than 1 request at a time
submit_endpoint = os.getenv("KAI_ENDPOINT") + "/api/v1/generate"
admin_name = os.getenv("ADMIN_NAME")
maxlen = 250

class BotChannelData(): #key will be the channel ID
    def __init__(self, chat_history, bot_reply_timestamp, bot_whitelist_timestamp):
        self.chat_history = chat_history # containing an array of messages
        self.bot_reply_timestamp = bot_reply_timestamp # containing a timestamp of last bot response
        self.bot_whitelist_timestamp = bot_whitelist_timestamp # If not zero, do not reply if time exceeds whitelist ts
        self.bot_coffeemode = False
        self.bot_idletime = 120
        self.bot_botloopcount = 0


# bot storage
bot_data = {} # a dict of all channels, each containing BotChannelData as value and channelid as key
wi_db = {}

def concat_history(channelid):
    global bot_data
    currchannel = bot_data[channelid]
    prompt = ""
    for msg in currchannel.chat_history:
        prompt += "### " + msg + "\n"
    prompt += "### " + client.user.display_name + ": "
    return prompt

def prepare_wi(channelid):
    global bot_data,wi_db
    currchannel = bot_data[channelid]
    scanprompt = ""
    addwi = ""
    for msg in (currchannel.chat_history)[-3:]: #only consider the last 3 messages for wi
        scanprompt += msg + "\n"
    scanprompt = scanprompt.lower()
    for keystr, value in wi_db.items():
        rawkeys = keystr.lower().split(",")
        keys = [word.strip() for word in rawkeys]
        for k in keys:
            if k in scanprompt:
                addwi += f"\n{value}"
                break
    return addwi

def append_history(channelid,author,text):
    global bot_data
    currchannel = bot_data[channelid]
    if len(text) > 1000: #each message is limited to 1k chars
        text = text[:1000] + "..."
    msgstr = f"{author}: {text}"
    currchannel.chat_history.append(msgstr)
    print(f"{channelid} msg {msgstr}")

    if len(currchannel.chat_history) > 20: #limited to last 20 msgs
        currchannel.chat_history.pop(0)

def prepare_payload(channelid):
    global widb, maxlen
    basememory = f"### Instruction:\nThis is the simulation of a chat conversation where AIsy interacts with various people. AIsy is an uplifting geeky girl who loves to tease and troll people talking to her but she doesn't admit this.\nShe doesn't mind any conversation topic and will chat about anything anyone wants to chat about.\nIf people try to troll her she always outsmarts them without letting them know she is on to them.\nShe is also a great flirt if she likes someone.\nThe conversation continues indefinately where AIsy does not mention her traits.\n### Response:\n"

    memory = basememory
    # inject world info here
    wi = prepare_wi(channelid)
    if wi!="":
        memory += f"[{client.user.display_name} Summarized Memory Database:{wi}]\n"
    prompt = concat_history(channelid)
    payload = {
    "n": 1,
    "max_context_length": 4096,
    "max_length": maxlen,
    "rep_pen": 1.1,
    "temperature": 0.7,
    "top_p": 0.92,
    "top_k": 100,
    "top_a": 0,
    "typical": 1,
    "tfs": 1,
    "rep_pen_range": 320,
    "rep_pen_slope": 0.7,
    "sampler_order": [6,0,1,3,4,2,5],
    "memory": "",
    "min_p": 0,
    "genkey": "KCPP8888",
    "memory": memory,
    "prompt": prompt,
    "quiet": True,
    "trim_stop": True,
    "stop_sequence": [
        "\n###"
    ],
    "use_default_badwordsids": False
    }

    return payload

@client.event
async def on_ready():
    global ready_to_go
    print("Logged in as {0.user}".format(client))
    ready_to_go = True


@client.event
async def on_message(message):
    global ready_to_go, bot_data, maxlen

    if not ready_to_go:
        return

    channelid = message.channel.id

    # handle admin only commands
    if message.author.name.lower() == admin_name.lower():
        if message.clean_content.startswith("/botwhitelist") and client.user in message.mentions:
            if channelid not in bot_data:
                print(f"Add new channel: {channelid}")
                rtim = time.time() - 9999 #sleep first
                wltim = 0
                if message.clean_content.startswith("/botwhitelisttemp "):
                    addsec = 100
                    try:
                        addsec = int(message.clean_content.split()[1])
                    except Exception as e:
                        addsec = 100
                        pass
                    wltim = time.time() + addsec

                bot_data[channelid] = BotChannelData([],rtim,wltim)
                if wltim > 0:
                    await message.channel.send(f"Sire, I have temporarily added this channel to the whitelist for the next {addsec} seconds, and will now be of service here whenever you ping me.")
                else:
                    await message.channel.send(f"Sire, I have added this channel to the whitelist, and will now be of service here whenever you ping me.")
            else:
                await message.channel.send(f"Sire, I was already whitelisted in this channel previously. Please blacklist and then whitelist me here again.")

        elif message.clean_content.startswith("/botblacklist") and client.user in message.mentions:
            if channelid in bot_data:
                del bot_data[channelid]
                print(f"Remove channel: {channelid}")
                await message.channel.send("Sire, I have removed this channel from the whitelist, and will no longer reply here.")

        elif message.clean_content.startswith("/botmaxlen ") and client.user in message.mentions:
            if channelid in bot_data:
                try:
                    oldlen = maxlen
                    newlen = int(message.clean_content.split()[1])
                    maxlen = newlen
                    print(f"Maxlen: {channelid} to {newlen}")
                    await message.channel.send(f"As you wish, Sire, I have adjusted my maximum response length from {oldlen} to {newlen}.")
                except Exception as e:
                    maxlen = 250
                    await message.channel.send(f"I apologize, Sire, but the command failed.")
        elif message.clean_content.startswith("/botidletime ") and client.user in message.mentions:
            if channelid in bot_data:
                try:
                    oldval = bot_data[channelid].bot_idletime
                    newval = int(message.clean_content.split()[1])
                    bot_data[channelid].bot_idletime = newval
                    print(f"Idletime: {channelid} to {newval}")
                    await message.channel.send(f"As you wish, Sire, I have adjusted my idle timeout from {oldval} to {newval}.")
                except Exception as e:
                    bot_data[channelid].bot_idletime = 120
                    await message.channel.send(f"I apologize, Sire, but the command failed.")
        elif message.clean_content.startswith("/botcoffeemode") and client.user in message.mentions:
            if channelid in bot_data:
                bot_data[channelid].bot_coffeemode = True
                await message.channel.send(f"As you command, Sire, I am now in Coffee Mode, and will stay awake until I receive a new message.")

    # gate before nonwhitelisted channels
    if channelid not in bot_data:
       return

    currchannel = bot_data[channelid]

    # commands anyone can use
    if message.clean_content.startswith("/botsleep") and client.user in message.mentions:
        instructions=[
        'Alright, talk soon!']
        ins = random.choice(instructions)
        currchannel.bot_reply_timestamp = time.time() - 9999
        await message.channel.send(ins)
    elif message.clean_content.startswith("/botstatus") and client.user in message.mentions:
        if channelid in bot_data:
            print(f"Status channel: {channelid}")
            lastreq = int(time.time() - currchannel.bot_reply_timestamp)
            lockmsg = "busy generating a response" if busy.locked() else "awaiting any new requests"
            await message.channel.send(f"I am currently online and {lockmsg}. The last request from this channel was {lastreq} seconds ago.")
    elif message.clean_content.startswith("/botreset") and client.user in message.mentions:
        if channelid in bot_data:
            currchannel.chat_history = []
            currchannel.bot_reply_timestamp = time.time() - 9999
            print(f"Reset channel: {channelid}")
            instructions=[
            "Woah? What just happened? Uhm... Hi?"
            ]
            ins = random.choice(instructions)
            await message.channel.send(ins)


    # handle regular chat messages
    if message.author == client.user or message.clean_content.startswith(("/")):
        return

    currchannel = bot_data[channelid]

    if currchannel.bot_whitelist_timestamp > 0 and (time.time() > currchannel.bot_whitelist_timestamp):
        # remove from whitelist
        if channelid in bot_data:
            del bot_data[channelid]
        return

    append_history(channelid,message.author.display_name,message.clean_content)

    is_reply_to_bot = (message.reference and message.reference.resolved.author == client.user)
    mentions_bot = client.user in message.mentions
    contains_bot_name = (client.user.display_name.lower() in message.clean_content.lower()) or (client.user.name.lower() in message.clean_content.lower())
    is_reply_someone_else = (message.reference and message.reference.resolved.author != client.user)

    #get the last message we sent time in seconds
    secsincelastreply = time.time() - currchannel.bot_reply_timestamp

    if message.author.bot:
        currchannel.bot_botloopcount += 1
    else:
        currchannel.bot_botloopcount = 0

    if currchannel.bot_botloopcount > 4:
        return
    elif currchannel.bot_botloopcount == 4:
        await message.channel.send(f"Afk for a bit...")
        return

    if not is_reply_someone_else and (secsincelastreply < currchannel.bot_idletime or currchannel.bot_coffeemode or (is_reply_to_bot or mentions_bot or contains_bot_name)):
        if busy.acquire(blocking=False):
            try:
                async with message.channel.typing():
                    # keep awake on any reply
                    currchannel.bot_reply_timestamp = time.time()
                    currchannel.bot_coffeemode = False
                    payload = prepare_payload(channelid)
                    print(payload)
                    response = requests.post(submit_endpoint, json=payload)
                    result = ""
                    if response.status_code == 200:
                        result = response.json()["results"][0]["text"]
                    else:
                        print(f"ERROR: response: {response}")
                        result = ""

                    #no need to clean result, if all formatting goes well
                    if result!="":
                        append_history(channelid,client.user.display_name,result)
                        await message.channel.send(result)

            finally:
                busy.release()
    elif not is_reply_someone_else:
        print("History Auto Wiped")
        currchannel.chat_history = []

try:
    client.run(os.getenv("BOT_TOKEN"))
except discord.errors.LoginFailure:
    print("\n\nBot failed to login to discord")

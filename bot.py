import asyncio
import subprocess
import shlex
import os
import re
from gtts import gTTS
import io
import discord
from discord.ext import commands
from discord.opus import Encoder

TOKEN = os.environ['DISCORD_BOT_TOKEN']
BOT_ID = int(os.environ['DISCORD_BOT_ID'])
LIMIT = 50
bot = commands.Bot(command_prefix='%')
channels = {}

class FFmpegPCMAudio(discord.AudioSource):
    def __init__(self, source, *, executable='ffmpeg', pipe=False, stderr=None, before_options=None, options=None):
        stdin = None if not pipe else source
        args = [executable]
        if isinstance(before_options, str):
            args.extend(shlex.split(before_options))
        args.append('-i')
        args.append('-' if pipe else source)
        args.extend(('-f', 's16le', '-ar', '48000', '-ac', '2', '-loglevel', 'warning'))
        if isinstance(options, str):
            args.extend(shlex.split(options))
        args.append('pipe:1')
        self._process = None
        try:
            self._process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
            self._stdout = io.BytesIO(
                self._process.communicate(input=stdin)[0]
            )
        except FileNotFoundError:
            raise discord.ClientException(executable + ' was not found.') from None
        except subprocess.SubprocessError as exc:
            raise discord.ClientException('Popen failed: {0.__class__.__name__}: {0}'.format(exc)) from exc
    def read(self):
        ret = self._stdout.read(Encoder.FRAME_SIZE)
        if len(ret) != Encoder.FRAME_SIZE:
            return b''
        return ret
    def cleanup(self):
        proc = self._process
        if proc is None:
            return
        proc.kill()
        if proc.poll() is None:
            proc.communicate()

        self._process = None

@bot.event
async def on_ready():
    activity = discord.Activity(name=f'%TTSheat - {len(bot.guilds)} servers', type=discord.ActivityType.watching)
    await bot.change_presence(activity=activity)

@bot.event
async def on_guild_join():
    activity = discord.Activity(name=f'%TTSheat - {len(bot.guilds)} servers', type=discord.ActivityType.watching)
    await bot.change_presence(activity=activity)

@bot.event
async def on_guild_remove():
    activity = discord.Activity(name=f'%TTSheat - {len(bot.guilds)} servers', type=discord.ActivityType.watching)
    await bot.change_presence(activity=activity)

@bot.command(aliases=['connect', 'con'])
async def join(ctx:commands.Context):
    if not ctx.message.guild:
        return
    if ctx.author.voice is None:
        await ctx.send('ボイスチャンネルに接続してから呼び出してください。')
        return
    if ctx.guild.voice_client:
        if ctx.author.voice.channel == ctx.guild.voice_client.channel:
            if channels.get(ctx.guild.id, -1) != ctx.channel.id:
                channels[ctx.guild.id] = ctx.channel.id
                await ctx.send('読み上げるチャンネルを変更しました。')
                return
            await ctx.send('接続済みです。')
            return
        else:
            channels.pop(ctx.guild.id, None)
            await ctx.voice_client.disconnect()
            await asyncio.sleep(0.5)
    await ctx.author.voice.channel.connect()
    channels[ctx.guild.id] = ctx.channel.id
    await ctx.send('接続しました。')

@bot.event
async def on_voice_state_update(member, before, after):
    vc = member.guild.voice_client
    if len(vc.channel.members) == 1 and BOT_ID == vc.channel.members[0].id:
        await vc.disconnect()
        await bot.get_channel(channels[member.guild.id]).send('切断しました。')

@bot.command(aliases=['discon', 'dcon', 'dc'])
async def disconnect(ctx:commands.Context):
    if not ctx.message.guild:
        return
    if ctx.voice_client is None:
        await ctx.send('ボイスチャンネルに接続していません。')
        return
    await ctx.voice_client.disconnect()
    channels.pop(ctx.guild, None)
    await ctx.send('切断しました。')

@bot.command(aliases=['TTSHEAT', 'ttsheat'])
async def TTSheat(ctx:commands.Context):
    await ctx.send(\
r'''```
%join : VCに接続
%dc   : VCから切断
```
一度の読み上げ上限は50文字です。
読み上げ速度変更、単語辞書には対応していません。
botがオンラインなのに死んだなと思ったら再度 `%join` してください。''')

@bot.event
async def on_message(message:discord.Message):
    await bot.process_commands(message)
    if message.author.bot or (not message.guild.voice_client) or (message.channel.id != channels.get(message.guild.id, -1)) or message.content.startswith('%'):
        return
    
    txt = message.content
    # arrange txt
    txt = txt.replace('\n', '、')
    # mentions
    match = re.findall(r'<@!(\d+)>', txt)
    for user_id in match:
        user = await bot.fetch_user(user_id)
        txt = re.sub(f'<@!{user_id}>', f'@{user.name}', txt)
    # roles
    match = re.findall(r'<@&(\d+)>', txt)
    for role_id in match:
        role = message.guild.get_role(int(role_id))
        txt = re.sub(f'<@&{role_id}>', f'@{role.name}', txt)
    # emojis
    match = re.findall(r'<:([a-zA-Z0-9_]+):\d+>', txt)
    for emoji_name in match:
        emoji_name = emoji_name.replace('_', '')
        txt = re.sub(rf'<:{emoji_name}:\d+>', f'{emoji_name}', txt)
    # urls
    images = {r'https://tenor.com/view/[\w/:%#\$&\?\(\)~\.=\+\-]+', r'https?://[\w/:%#\$&\?\(\)~\.=\+\-]+(\.jpg|\.jpeg|\.gif|\.png|\.bmp)'}
    for image in images:
        txt = re.sub(image, '画像', txt)
    txt = re.sub(r'https?://[\w/:%#\$&\?\(\)~\.=\+\-]+', 'URL', txt)
    
    mp3_fp = io.BytesIO()
    tts = gTTS(text=txt[:LIMIT], lang='ja')
    tts.write_to_fp(mp3_fp)
    mp3_fp.seek(0)
    file = FFmpegPCMAudio(mp3_fp.read(), pipe=True)
    while message.guild.voice_client.is_playing():
        await asyncio.sleep(0.5)
    message.guild.voice_client.play(file)

if __name__ == '__main__':
    bot.run(TOKEN)
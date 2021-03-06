from plexapi.myplex import MyPlexAccount
import configparser
import discord
import asyncio
import subprocess
import os
import time
import string
from multiprocessing import Process
import validators
from urllib.parse import urlsplit
import secrets
# Read in config
config = configparser.ConfigParser()
config.read(os.path.dirname(os.path.realpath(__file__)) +'/config.ini')
os.chdir(os.path.dirname(os.path.realpath(__file__)))
# Connect to plex server
account = MyPlexAccount(config['plex']['Username'], config['plex']['Password'])
plex = account.resource(config['plex']['Server']).connect() 
# Global variables to handle state
videoPlaying = False
ffmpegID = 0
# Define discord client
client = discord.Client()    

def startStream(message,path,id):
    global client
    # Update path so its accurate on the stream server
    for x in config['plex']['RemappedFolders'].split(","):
        oldPath, newPath = x.split(":")
        path = path.replace(oldPath, newPath)
    url = config['stream']['Destination'] + id
    # Start streaming the video using ffmpeg
    subprocess.call([config['stream']['FFMPEGLocation'], "-re", "-i", path, "-c:v", "libx264", "-filter:v", "scale=1280:trunc(ow/a/2)*2", "-preset", "fast", "-minrate", "500k", "-maxrate", "3500k", "-bufsize", "12M", "-c:a", "libfdk_aac", "-b:a", "160k", "-f", "flv", url ])



# Just so you know your connected
@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
    await client.change_presence(game=discord.Game(name=None))

# On Discord message
@client.event
async def on_message(message):
    global videoPlaying
    global ffmpegID
    # Message is for searching
    if message.content.startswith('!search'):
        # Define blank message
        msg = ''
        # Get the name of the movie from the message
        name = message.content[len('!search'):].strip()
        # Define the movie library
        movies = plex.library.section('Movies')
        if len(movies.search(name))>0:
            # Loop through the search results and add them to the message
            for video in movies.search(name):
                msg += '`'+video.title+'`\r'
        else:
            msg = 'No movie found'
        # Send message with search results
        await client.send_message(message.channel, msg)
    # Message is command to play movie
    elif message.content.startswith('!play'):
        # If a movie is already playing discard message and notify
        if videoPlaying == True:
            await client.send_message(message.channel, 'Stream is already playing')
        else:
            msg = ''
            name = message.content[len('!play'):].strip()
            # Get movie information from plex
            try:
                movie = plex.library.section('Movies').get(name)
            except:
                search = plex.library.section('Movies').search(name)
                if len(search) == 1:
                    movie = search[0]
      
            # Set the game the bot is playing to the movie name
            await client.change_presence(game=discord.Game(name=movie.title))
            # Set the global movie playing variable so there aren't duplicate videos trying to stream
            videoPlaying = True
            streamID = secrets.token_urlsafe(8)
            # Send message to confirm action
            await client.send_message(message.channel, 'Streaming '+movie.title+'\rhttps://stream.vangel.io/?='+streamID)
            p = Process(target=startStream, args=(message,movie.locations[0],streamID,))
            p.start()
    # Video stop command
    elif message.content.startswith('!stop'):
        try:
            ffmpegID = subprocess.check_output(["pgrep", "ffmpeg"]).strip().decode('ascii')
            # Kill the ffmpeg process
            subprocess.run(["kill",ffmpegID])
        except:
            print("No video playing")
        # Clear the game playing information
        await client.change_presence(game=discord.Game(name=None))
        # Set the video playing variable to false to allow a new video to be streamed
        videoPlaying = False
        # Send message to confirm action
        await client.send_message(message.channel, 'Stopping Stream')
    # Pause command
    elif message.content.startswith('!pause'):
        ffmpegID = subprocess.check_output(["pgrep", "ffmpeg"]).strip().decode('ascii')
        # Suspend the ffmpeg process
        subprocess.run(["kill", "-s", "SIGSTOP",ffmpegID])
        # Send message to confirm action
        await client.send_message(message.channel, 'Pausing Stream')
    elif message.content.startswith('!resume'):
        ffmpegID = subprocess.check_output(["pgrep", "ffmpeg"]).strip().decode('ascii')
        # Resume the ffmpeg process
        subprocess.run(["kill", "-s", "SIGCONT", ffmpegID])
        # Send message to confirm action
        await client.send_message(message.channel, 'Resuming Stream')
    # Print out commands available
    elif message.content.startswith('!help'):
        await client.send_message(message.channel, '**!search {movie}** Search for a movie by name\r**!play {movie}** Play a movie using the exact name from the search command\r**!pause** Pause the movie\r**!resume** Resume the paused movie\r**!stop** Stop the movie\r**!tvsearch {tv_name}** Search for a tv show by name\r**!tvplay {tv_name} -s={season_number} -e={episode_number}** Play an episode of TV')
    elif message.content.startswith('!tvsearch'):
        # Define blank message
        msg = ''
        # Get the name of the video from the message
        name = message.content[len('!tvsearch'):].strip()
        # Define the tv library
        tv = plex.library.section('TV Shows')
        if len(tv.search(name)) > 0:
            # Loop through the search results and add them to the message
            for video in tv.search(name):
                msg = msg + "```\r"+video.title
                for season in video.seasons():
                    msg = msg + "\rSeason "+ str(season.index)+"\r"
                    for episode in season.episodes():
                        msg = msg + str(episode.index) + " "
            msg = msg + '```'
        else:
            msg = 'No TV show found'
        # Send message with search results
        await client.send_message(message.channel, msg)
    elif message.content.startswith('!tvplay'):
        # Define blank message
        msg = ''
        # Get the name of tv from the message
        season = message.content.find("-s=")
        episode = message.content.find("-e=")
        name = message.content[len('!tvplay'):season].strip()
        seasonNumber = message.content[season+3:episode].strip()
        episodeNumber = message.content[episode+3:].strip()
        # Define the tv library
        tv = plex.library.section('TV Shows')
        searchResult = tv.search(name)
        print(searchResult)
        if len(searchResult) > 1:
            await client.send_message(message.channel, 'Refine search result to one show')
        elif len(searchResult) > 0:
            # Loop through the search results and add them to the message
            for video in searchResult:
                for season in video.seasons():
                    for episode in season.episodes():
                        if str(season.index) == str(seasonNumber) and str(episode.index) == str(episodeNumber):
                            await client.change_presence(game=discord.Game(name=episode.title))
                            # Set the global video playing variable so there aren't duplicate videos trying to stream
                            videoPlaying = True
                            streamID = secrets.token_urlsafe(8)
                            ## Send message to confirm action
                            await client.send_message(message.channel, 'Streaming '+episode.title+'\rhttps://stream.vangel.io/?='+streamID)
                            p = Process(target=startStream, args=(message,episode.locations[0],streamID,))
                            p.start()
           
        else:
            await client.send_message(message.channel, 'No episode or TV show matching that name found')

    elif message.content.startswith('!update'):
        authorizedUsers = config['discord']['AuthorizedUsers'].split(',')
        userID = message.author.id
        if userID in authorizedUsers:
            subprocess.run(["git", "fetch", "origin"])
            out = subprocess.check_output(["git", "rev-list", "--count", "origin/master...master"])
            commitsBehind = int(str(out.decode("utf-8")).rstrip())
            if commitsBehind > 0 and videoPlaying == False:
                await client.send_message(message.channel, 'You are '+str(out.decode("utf-8")).rstrip()+' commits behind')
                await client.send_message(message.channel, 'Updating')
                videoPlaying = True
                subprocess.run(["git", "reset", "--hard", "origin/master"])
                subprocess.run(["systemctl", "restart", "videobot"])
            elif commitsBehind > 0 and videoPlaying == True:
                await client.send_message(message.channel, 'You are '+str(out.decode("utf-8")).rstrip()+' commits behind')
                await client.send_message(message.channel, 'Run this command when a video isn\'t streaming to update')
            else:
                await client.send_message(message.channel, 'Videobot is up to date')
        else:
            await client.send_message(message.channel, 'Unauthorized User')
    # elif message.content.startswith('!youtubeplay'):
    #     name = message.content[len('!youtubeplay'):].strip()
    #     if validators.url(name) == True:
    #         parsed_uri = urlsplit(name)
    #         if parsed_uri.hostname == "www.youtube.com" or parsed_uri.hostname == "youtube.com" or parsed_uri.hostname == "youtu.be"  or parsed_uri.hostname == "www.youtu.be":
    #             await client.change_presence(game=discord.Game(name='Youtube'))
    #             # Set the global movie playing variable so there aren't duplicate movies trying to stream
    #             videoPlaying = True
    #             ## Send message to confirm action
    #             await client.send_message(message.channel, 'Streaming Youtube')
                
    #             devnull = open('/dev/null', 'w')
    #             # Start streaming the movie using ffmpeg
    #             # Path to movie is pulled from the plex api because the paths are the same on both machines
    #             command = "youtube-dl -f 'best[ext=mp4]' -o - \""+name+"\" | ffmpeg -re -i pipe:0 -c:v copy -preset fast -c:a copy -f flv "+ config['stream']['Destination']
    #             print(command)
    #             subprocess.call(command.split(), shell=False)
    #     else:
    #         await client.send_message(message.channel, 'Invalid url')

# Start discord client
client.run(config['discord']['Key'])


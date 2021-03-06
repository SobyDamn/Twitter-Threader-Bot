import tweepy
import time
import logging
import random
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
from os import environ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
# Authenticating to to Twitter
API_KEY = environ["API_KEY"]
API_SKEY = environ["API_SKEY"]
ACC_Token = environ["ACC_Token"]
ACC_Token_Secret = environ["ACC_Token_Secret"]
auth = tweepy.OAuthHandler(API_KEY,API_SKEY)
auth.set_access_token(ACC_Token,ACC_Token_Secret)
api = tweepy.API(auth, wait_on_rate_limit=False,
    wait_on_rate_limit_notify=False)
#Credential for firebase
google_creds = {
    "type": "service_account",
    "project_id": "twitter-threader",
    "private_key_id": environ["private_key_id"],
    "private_key": environ["private_key"].replace("\\n", "\n"),
    "client_email": environ["client_email"],
    "client_id": environ["client_id"],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-rh7d4%40twitter-threader.iam.gserviceaccount.com"
    }
cred = credentials.Certificate(google_creds)

class userThread:
    def __init__(self,id, name,username,profile_img,tweets):
        '''
        id: profile id of thread owner
        '''
        self.id = id
        self.name = name
        self.username = username
        self.tweets = tweets
        self.profile_img = profile_img
    def to_dict(self):
        obj = {
            'id':self.id,
            'name':self.name,
            'username':self.username,
            'profile_img':self.profile_img,
            'tweets':[]
        }
        for tweet in self.tweets:
            tweet_id = tweet.tweet_id
            obj['tweets'].append(tweet.to_dict())
        return obj
class Tweet:
    def __init__(self, text,date,medias,tweet_id,urls):
        self.text = text
        self.date = date
        self.medias = medias
        self.tweet_id = tweet_id
        self.urls = urls ##contains list either empty or list with object url,expanded_url,display_url(sliced urls)
    def to_dict(self):
        obj = {
            'text':self.text,
            'date':self.date,
            'tweet_id':str(self.tweet_id),
            'urls':self.urls,
            'medias':self.medias
        }
        return obj
class ThreadCompiler:
    def __init__(self,tweet_id,user_id,thread_request_id,easy_compile=True,max_tweets_to_look=5000):
        '''
        tweet_id - the id of the tweet under which user requested
        user_id - id of the thread owner
        thread_request_id - id of the user's tweet who requested thread compile
        easy_compile - rolling up to the parent (use when thread is too old)
        '''
        self.tweet_id = tweet_id
        self.id = tweet_id ##storing parent id
        self.user_id = user_id #thread_user_ids
        self.tweets = None
        self.max_tweets_to_look = max_tweets_to_look
        self.thread_request_id = thread_request_id
        self.easy_compile = easy_compile #if easy compile we won't be checking Bottom thread just roll to the parent of thread
    def compileTweets(self):
        '''
        Compiles tweet of thread
        Compile to the parent of the child
        return list of object of class type Tweet
        '''
        self.tweets = []
        parent_tweet_id = self.tweet_id
        print("ThreadCompiler: Fetching Head thread!")
        while parent_tweet_id:
            try:
                tweet = api.get_status(parent_tweet_id, tweet_mode="extended")
                if tweet.user.id != self.user_id:
                    break
                medias = []
                if hasattr(tweet,"extended_entities"):
                    if "media" in tweet.extended_entities:
                        media_entities = tweet.extended_entities['media']
                        for media_data in media_entities:
                            media = {}
                            ##Currently only planning to save photo data as it'll be transformed to PDF
                            if media_data['type']=='photo' or media_data['type'] == 'video':
                                media['type'] = media_data['type']
                                media['media_url_https'] = media_data['media_url_https']
                                media['media_url'] = media_data['media_url']
                                media['expanded_url'] = media_data['expanded_url']
                                medias.append(media)
                tweetObj = Tweet(tweet.full_text,str(tweet.created_at),list(medias),parent_tweet_id,tweet.entities['urls'])
                self.tweets.append(tweetObj)
                parent_tweet_id = tweet.in_reply_to_status_id
            except tweepy.TweepError as e:
                print("ThreadCompiler:TweepyError {}".format(e))
                #Send Response to user and end the compilation
                raise Exception("Compiling thread top error!")
                break
        self.tweets = self.tweets[::-1]
        if self.easy_compile:
            print("ThreadCompiler:Easy Compile Requested!")
            return self.tweets
        else:
            return self.tweetCompilerBottom()
        #return list(self.tweets)
    def tweetCompilerBottom(self,since_id=None):
        '''
        Compiles the bottom half of the tweet by looking for child
        '''
        print("ThreadCompiler:Fetching Bottom thread!")
        if not since_id:
            looking_for = self.tweet_id
        tweets = tweepy.Cursor(api.user_timeline,user_id=self.user_id,since_id=looking_for,trim_user=True,include_rts=False,exclude_replies=False,tweet_mode="extended").items()
        tweets_track = {} ##contains all tweets traced
        bottom_thread_exists = False
        for i in range(self.max_tweets_to_look):
            try:
                if i%50==0:
                    print("ThreadCompiler: Searched {} so far.".format(i))
                tweet = tweets.next()
                if hasattr(tweet, 'in_reply_to_status_id_str') and tweet.in_reply_to_status_id and tweet.id != self.thread_request_id:
                    medias = []
                    if hasattr(tweet,"extended_entities"):
                        if "media" in tweet.extended_entities:
                            media_entities = tweet.extended_entities['media']
                            for media_data in media_entities:
                                media = {}
                                ##Currently only planning to save photo data as it'll be transformed to PDF
                                if media_data['type']=='photo' or media_data['type'] == 'video':
                                    media['type'] = media_data['type']
                                    media['media_url_https'] = media_data['media_url_https']
                                    media['media_url'] = media_data['media_url']
                                    media['expanded_url'] = media_data['expanded_url']
                                    medias.append(media)
                    tweetObj = Tweet(tweet.full_text,str(tweet.created_at),list(medias),tweet.id,tweet.entities['urls'])
                    #Saving track with respect to in_reply_to_status_id ez to look for thread
                    #print(i)
                    tweets_track[tweet.id] = {
                        "tweet":tweetObj,
                        "in_reply_to_status_id":tweet.in_reply_to_status_id
                    }
            except StopIteration:
                bottom_thread_exists = True #No more results might have reached to since_id and hence thread exists
                print("ThreadCompiler: BottomThread - No more result found")
                break
            except tweepy.RateLimitError as e:
                logging.error("Twitter api rate limit reached Error-{}".format(e))
                time.sleep(60) ##Sleep and retry after a while
                continue
            except tweepy.TweepError as e:
                print("ThreadCompiler:TweepyError {}".format(e))
                #Send Response to user and end the compilation
                raise Exception("Compiling bottom thread error!")
                break
        #return tweets_track
        if bottom_thread_exists:
            self.fetchBottomThread(tweets_track)
        else:
            #Respone thread is to old
            raise Exception("ThreadCompiler:Thread is too old or too many tweets!")
            pass
        return self.tweets
    def fetchBottomThread(self,tweets_track,tweet_id=None):
        if not tweet_id:
            tweet_id = self.tweet_id
        '''
        Finding Longest Thread till tweet_id
        if multiple exists returns the on which comes first
        '''
        print("ThreadCompiler:Cooking Bottom Threads!")
        i=0
        threads = {}
        while i<len(list(tweets_track)):
            looking_for = list(tweets_track)[i]
            child_id = looking_for
            i +=1
            count = 0
            possible_threads = []
            while looking_for:
                if looking_for in tweets_track:
                    count +=1
                    possible_threads.append(tweets_track[looking_for]['tweet'])
                    looking_for = tweets_track[looking_for]["in_reply_to_status_id"]
                elif looking_for == tweet_id: #Thread I was looking for
                    threads[child_id] = possible_threads
                    break
                else:
                    break
            #i += count - 1
        if len(threads) > 0:
            thread_id = max(threads, key=lambda k: len(threads[k]))
            self.tweets += threads[thread_id][::-1]
            print("ThreadCompiler:Bottom Threads prepared!")
            return threads[thread_id][::-1]
        else:
            print("ThreadCompiler:Bottom Thread does not exists!")
            return
    def compileThread(self):
        '''
        Compiles Thread of tweets and user and return object of class type userThread
        '''
        print("ThreadCompiler: Compiling Thread")
        if not self.tweets:
            self.compileTweets()
        self.id = self.tweets[0].tweet_id ##first id is used to save the thread
        user = api.get_user(self.user_id)
        return userThread(self.user_id,user.name,user.screen_name,user.profile_image_url_https,self.tweets)
    def save(self,threaData:"Dictionar"=None):
        '''
        threaData: Takes dictionary
        saves it to the firebase if not already exists and return True
        '''
        ##
        if not threaData:
            threaData = self.compileThread().to_dict()
        print("ThreadCompiler: Preparing to save!")
        FU = FirebaseUtility(cred)
        FU.storeData(self.id,threaData)
        return True
    def getThreadID(self):
        '''
        Returns the thread id
        Used to access documents
        '''
        return str(self.id)
class FirebaseUtility:
    def __init__(self,cred):
        self.cred = cred
        self.initialize() ##initialise first
        self.db = firestore.client()
            
    def initialize(self):
        try:
            if not firebase_admin._apps:
                print("FirebaseUtility:Initializing")
                firebase_admin.initialize_app(self.cred)
        except:
            print("FirebaseUtility:Error in cred FIX NEEDED!")
    def botWorkerUtils(self,read=True,data=None):
        '''
        Method exclusive for hosting bot on platform like heroku like platform which resets the files in the directory whenever restarts
        if read, it'll return the stored data else will be storing the given data
        '''
        doc_ref = self.db.collection(u'botData').document('lastMentions')
        if read:
            doc = doc_ref.get()
            #mode is read just return the data from firestore
            if doc.exists:
                #print("FirebaseUtility: Reading since_id from firestore!")
                return doc.to_dict()['since_id']
            else:
                raise Exception("FirebaseUtility:No bot data found in the location botData/lastMentions with name since_id")
        else:
            #mode is write just add data to the firestore
            if data:
                val = {'since_id':str(data)}
                #print("FirebaseUtility: Saving since_id - {} to firestore!".format(str(data)))
                doc_ref.set(val)
                return True
            else:
                raise Exception("FirebaseUtility:No data to set")
    def documentExists(self,thread_id:"Thread parent id",thread_len:"Length of fetched thread"):
        doc_ref = self.db.collection(u'threads').document(str(thread_id))
        doc = doc = doc_ref.get()
        if doc.exists:
            if len(doc.to_dict()['tweets']) < thread_len:
                print("FirebaseUtility:Thread Already Exists but shorter")
                return False
            else:
                print("FirebaseUtility:Thread Already Exists")
                return True
        else:
            print('FirebaseUtility:No such Thread!')
            return False
    def storeData(self,thread_id,data:"dictionary"):
        '''
        Stores the dictionary data with document name thread_id
        '''
        if not self.documentExists(thread_id,len(data['tweets'])):
            doc_ref = self.db.collection(u'threads').document(str(thread_id))
            doc_ref.set(data)
            print('FirebaseUtility:Thread {} Stored!'.format(str(thread_id)))
        else:
            pass
class ThreaderBot:
    def __init__(self,file_name="since_id.txt"):
        self.since_id = self.read_write_since_id()
    def retrieve_since_id(self,file_name="since_id.txt"):
        fread = open(file_name, 'r')
        since_id = int(fread.read().strip())
        fread.close()
        return since_id
    def store_since_id(self,since_id, file_name="since_id.txt"):
        fwrite = open(file_name, 'w')
        fwrite.write(str(since_id))
        fwrite.close()
        return

    def read_write_since_id(self,read=True,data=None):
        '''
        Working from database
        '''
        FU = FirebaseUtility(cred)
        return FU.botWorkerUtils(read,data)
    def fetchTweets(self):
        '''
        Fetches only mentioned tweets
        retweet will trigger this aswell
        '''
        try:
            self.since_id = self.read_write_since_id()
            mentions = api.mentions_timeline(self.since_id)
            mention = mentions[0] if len(mentions) !=0 else None
            if mention:
                print("Storing The last mentioned",mention.id)
                since_id = mention.id #Store the last id so that we can keep ourself updated
                self.read_write_since_id(False,since_id)
                #self.store_since_id(since_id)
                self.since_id = since_id #Update the bot aswell
            return mentions
        except tweepy.RateLimitError as e:
            sleepTime = 120 #In seconds
            logging.error("ThreaderBot - Fetchingtweet(): Twitter api rate limit reached Error Sleeping for {}, Error-{}".format(sleepTime,e))
            time.sleep(sleepTime) ##Sleep and retry after a while
            return
        except tweepy.TweepError as e:
            logging.error("ThreaderBot - Fetchingtweet(): Twitter api Error {}".format(e))
            return
    def run(self):
        '''
        Returns unique list of recently mentioned tweets
        in_reply_to_status_id,in_reply_to_user_id,requested user screen_name and
        request_id - id of the tweet request
        Note:Twitter doesn't allow to tweet same tweet to same reply
        '''
        #print("ThreaderBot: Running...")
        tweets = self.fetchTweets()
        if not tweets:
            #print("ThreaderBot: Nothing New!")
            return False
        else:
            print("ThreaderBot: Threading...")
            request_details = []
            for tweet in tweets:
                if "ping" in tweet.text.lower():
                    self.sendResponse("Pong!",tweet.user.screen_name,tweet.id)
                if hasattr(tweet, 'in_reply_to_status_id_str') and tweet.in_reply_to_status_id:
                    tweetTxt = tweet.text.lower()
                    if "compile" in tweetTxt.split(" ") or "ezcompile" in tweetTxt.split(" "):
                        dm_request = False
                        easy_compile = True
                        if "compile" in tweetTxt.split(" "):
                            easy_compile = False
                        elif "compile" and "ezcompile" in tweetTxt.split(" "):
                            easy_compile = True
                        if "dm" in tweetTxt.split(" "):
                            dm_request = True
                        request_details.append((tweet.in_reply_to_status_id,tweet.in_reply_to_user_id,tweet.user.screen_name,tweet.user.id,tweet.id,easy_compile,dm_request))
                    else:
                        print("ThreaderBot: Nevermind")
                else:
                    print("ThreaderBot: Nothing to compile")
            return request_details if len(request_details) > 0 else False
    def sendResponse(self,text,request_username,rquest_id):
        '''
        Send response who requested the thread
        username is required to reply
        Note: make sure that twitter api project is created under read and write
        '''
        response = "@"+request_username+" "+str(text)
        try:
            api.update_status(response,in_reply_to_status_id=rquest_id,possibly_sensitive=False)
            print("Response sent successfully")
        except tweepy.TweepError as e:
            print("ThreaderBot:Error replying '{}' to the tweet, {}".format(text,e))
    def sendResponseDirectMessage(self,text,id):
        '''
        Send response who requested the thread
        Note: make sure that twitter api project is created under read, write and dm
        '''
        response = str(text)
        
        try:
            api.send_direct_message(recipient_id=id,text=response)
            print("Response sent as DM successfully")
        except tweepy.TweepError as e:
            print("ThreaderBot:Error in sending '{}' as dm response, {}".format(text,e))
def responseGen(link,tweetText,thread_len):
    response_first_half = ["Hey check the compiled thread of length {} - ".format(str(thread_len)),"Requested thread of size {} - compiled ".format(str(thread_len)),"Here is your requested thread - ","Always here to help check your thread - ","Happy to help you thread is compiled - ","Look what I cooked,it's your thread - ","Sup buddy,requested something? Here it is - ","That was tough still I made it for you check your compiled thread - ","Sorry for the delay, Here is your compilation - ","Ai! Ai! Captain,Your thread - ","Yoda I am! and thread here is - ","Tough day? well I can't do any thing except this beautiful thread - ","I am Alive!..oops..here is what you requested - ","Hola! take it - "]
    response_last_part = ["Read it here \n","check here \n","Here - ","Visit - ","here you go \n","Read here \n"]
    startText = response_first_half[random.randint(0,len(response_first_half)-1)]
    endText = response_last_part[random.randint(0,len(response_last_part)-1)]
    textLength = 270 - (len(startText)+len(endText)+len(link)+random.randint(5,20))
    response = startText + '"{}...." '.format(tweetText[0:textLength]) + endText + link
    return response
def surfBot(bot:"ThreadBot"):
    '''
    Runs the bot and make him awake
    '''
    requests = bot.run()
    if requests:
        for in_reply_to_tweet_id,in_reply_to_user_id,request_username,request_user_id,request_id,easy_compile,dm_request in requests:
            try:
                compiler = ThreadCompiler(in_reply_to_tweet_id,in_reply_to_user_id,request_id,easy_compile)
                if compiler.save():
                    firstTweetText = compiler.tweets[0].text
                    link ="https://sobydamn.github.io/TwitterThread/threads/thread.html?threadID="+str(compiler.id)
                    text = responseGen(link,firstTweetText,len(compiler.tweets))
                    if dm_request:
                        bot.sendResponseDirectMessage(text,request_user_id)
                    else:
                        bot.sendResponse(text,request_username,request_id)
                else:
                    #print("Bot Surfer:Nothing Requested!")
                    return
            except Exception as e:
                ##Send response as we got error
                text = "Looks Like thread is too old or something went wrong!\nTry different method check here for help - https://sobydamn.github.io/TwitterThread/"
                bot.sendResponse(text,request_username,request_id)
                print("SurfBot: Error - {}".format(e))
bot = ThreaderBot()
##Surfing using bot
#Deploying
print("Surfing bot......")
while True:
    surfBot(bot)
    time.sleep(30) #30 sec
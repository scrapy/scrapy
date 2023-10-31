from bs4 import BeautifulSoup
import requests
import googleapiclient.discovery
import googleapiclient.errors
import pandas as pd
def get_yt_data(x):
    y = x.split('=')
    api_service_name = "youtube"
    api_version = ""#your API version
    DEVELOPER_KEY = ""#your developer key

    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, developerKey = DEVELOPER_KEY)

    request = youtube.commentThreads().list(
        part = "snippet",
        videoId = y[1],
        maxResults = 100
    )
    response = request.execute()
    comments = []
    for item in response['items']:
      comment = item['snippet']['topLevelComment']['snippet']
      comments.append([
          comment['authorDisplayName'],
          comment['publishedAt'],
          comment['updatedAt'],
          comment['likeCount'],
          comment['textDisplay']
      ])
    df = pd.DataFrame(comments, columns=['author', 'published_at', 'updated_at', 'like_count', 'text'])
    print(df)
"""Original identities and stable traits. No source player names are exported."""
from random import Random
from .contracts import Club, Player

CLUBS=[('eastbridge','Eastbridge','EB','#163c32'),('northport','Northport','NP','#183d64'),
       ('southbank','Southbank','SB','#78395a'),('redhaven','Redhaven','RH','#bc432e'),
       ('westmere','Westmere','WM','#375e77'),('oakfield','Oakfield','OF','#54633d'),
       ('kingswell','Kingswell','KW','#654b79'),('riverside','Riverside','RS','#467b7d'),
       ('hillcrest','Hillcrest','HC','#665c40'),('stonegate','Stonegate','SG','#4b5269'),
       ('fairmont','Fairmont','FM','#7f534b'),('brookvale','Brookvale','BV','#466d56')]
NAMES=[
 ['Theo Ashford','Finn Brooks','Oliver Hayes','Alex Rowan','Elliot Reed','Jamie Vale','Lucas Hart','Kai Mercer','Rory Ellis','Milo West','Owen Cole'],
 ['Arthur Wells','Ben Fletcher','Callum Stone','Noah Arden','Dylan Frost','Sam Linden','Evan Shore','Leo Marlow','Henry Blake','Isaac Lane','Jude Rivers'],
 ['Leon Finch','Adam Keene','Felix Ward','Toby Quinn','Max Harlow','Nico Alder','Zane Bell','Remy Sutton','Dario Voss','Eli Marsh','Asa Hale'],
 ['Rafael Wynn','Hugo Dane','Joel Perry','Luca Bennett','Oscar Penn','Ruben Silva','Tariq Moss','Enzo Clarke','Mateo Cross','Seth Nolan','Amir Rhodes'],
]
ROLES=['GK','DF','DF','MF','DF','MF','FW','MF','FW','DF','FW','DF','MF','FW','GK']


def build_registry(model,seed=20261020):
    rng=Random(seed);clubs=[];players=[]
    first=['Aiden','Bram','Casper','Devon','Emil','Florian','Gavin','Ilan','Jonas','Kian','Lewis','Marek','Nolan','Orson','Pavel']
    last=['Ainsley','Bexley','Corbin','Darby','Elwood','Fenton','Granville','Hadley','Ingle','Jarvis','Kendall','Langley']
    for c,(cid,name,prefix,color) in enumerate(CLUBS):
        clubs.append(Club(club_id=cid,name=name,short_name=prefix,featured=c<4,primary_color=color))
        for i,role in enumerate(ROLES,1):
            pid=f'{prefix.lower()}{i:02}'
            name=NAMES[c][i-1] if c<4 and i<=11 else f'{first[i-1]} {last[c]}'
            rates=model['role_rates'][role]['pass'];spread=min(.35,rates['sd']/max(1,rates['mean']))
            star=c<4 and i in (8,9)
            involvement=min(1.7,max(.55,rng.lognormvariate(-spread**2/2,spread)))
            if star:involvement=min(1.8,max(1.25,rates['p90']/max(1,rates['mean'])))
            accuracy=model['role_rates'][role]['pass_accuracy']
            passing=max(-.08,min(.06,rng.gauss(0,accuracy['sd'])))
            if star:passing=max(passing,.025)
            players.append(Player(player_id=pid,club_id=cid,name=name,role=role,number=i,featured=c<4 and i<=11,
                star=star,birth_year=1999+rng.randrange(4),involvement=round(involvement,5),passing=round(passing,5),
                finishing=round(1.3 if star and role=='FW' else rng.uniform(.85,1.15),5)))
    return clubs,players

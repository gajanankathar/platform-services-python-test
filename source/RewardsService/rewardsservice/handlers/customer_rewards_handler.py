import json
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, MongoClient

from tornado.escape import json_encode, json_decode
from tornado.gen import coroutine
import tornado.web


class CustomerRewardsHandler(tornado.web.RequestHandler):

    def initialize(self):
        self.client = MongoClient("mongodb", 27017)
        self.db = self.client['Rewards']

    @staticmethod
    def _calculate_points(amount, available_points=0):
        return int(amount or 0) + available_points

    def _calculate_progress(self, points):
        top_reward_prg = self.get_top_reward()
        if points > top_reward_prg.get("points"):
            return 100
        curr_reward_prg = self.get_current_reward_program(points)
        nxt_reward_prg = self.get_next_reward_program(points)
        diff = nxt_reward_prg.get("points") - curr_reward_prg.get("points", 0)
        rem = points % 100 if points > 100 else points
        return round((rem/diff) * 100, 2)

    def get_customer_available_points(self, email):
        customer = self.db.customers.find_one({"email": email})
        return customer.get("points") if customer else 0

    def get_top_reward(self):
        return self.db.rewards.find_one({}, sort=[("points", DESCENDING)]) or {}

    def get_current_reward_program(self, points):
        top_reward_prg = self.get_top_reward()
        if points > top_reward_prg.get("points"):
            return top_reward_prg
        lower_bound = points - 100
        return self.db.rewards.find_one({
            "$and": [{"points": {"$gt": lower_bound}}, {"points": {"$lte": points}}]
        }) or {}

    def get_next_reward_program(self, points):
        top_reward_prg = self.get_top_reward()
        if points > top_reward_prg.get("points"):
            return top_reward_prg
        upper_bound = points + 100
        return self.db.rewards.find_one({
            "$and": [{"points": {"$gt": points}}, {"points": {"$lte": upper_bound}}]
        }) or {}

    @coroutine
    def post(self):
        customer = json_decode(self.request.body)
        available_points = self.get_customer_available_points(customer.get("emailId"))
        top_reward_prg = self.get_top_reward()
        if available_points < top_reward_prg.get("points"):
            points = self._calculate_points(customer.get("orderTotal"), available_points)
            curr_reward_prg = self.get_current_reward_program(points)
            print("Current ", curr_reward_prg)
            nxt_reward_prg = self.get_next_reward_program(points)
            print("Next ", nxt_reward_prg)
            customer.update({
                "_id": str(ObjectId()),
                "points": points,
                "tier": curr_reward_prg.get("tier"),
                "rewardName": curr_reward_prg.get("rewardName"),
                "nextTier": nxt_reward_prg.get("tier"),
                "nextRewardName": nxt_reward_prg.get("rewardName"),
                "nextRewardTierAwayPercentage": (100 - self._calculate_progress(points)),  # Away from next program
            })

            del customer["orderTotal"]
            print("customer", customer)
            created_customer = self.db.customers.insert_one(customer)
            self.set_status(201)
            self.write(json_encode({"message": "Customer rewards created/updated successfully!"}))
        else:
            self.set_status(200)
            self.write(json_encode({"message": "You cann't earn more rewards as you reach to the top."}))

    @coroutine
    def get(self):
        customers = list(self.db.customers.find({}, {"_id": 0}))
        self.set_status(200)
        self.write(json.dumps(customers))

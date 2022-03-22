# sample links
# https://courses.students.ubc.ca/cs/courseschedule?pname=subjarea&tname=subj-all-departments
# https://courses.students.ubc.ca/cs/courseschedule?pname=subjarea&tname=subj-department&dept=AANB
# https://courses.students.ubc.ca/cs/courseschedule?pname=subjarea&tname=subj-course&dept=AANB&course=530A

import traceback
from bs4 import BeautifulSoup
import re
import copy

from ..utils.selenium import driver
from ..utils.url import generateUrl

RE_STRING_PREREQ = re.compile('^(?:Pre-reqs).*$')
RE_STRING_COREQ = re.compile('^(Co-req).*$')
RE_STRING_NOOFFER = re.compile('no longer offered')

RE_STRING_REQUIRED_COURSES = [
    [0, re.compile('(?:All of|all of)')],
    [1, re.compile('(?:One of|one of)')],
    [2, re.compile('(?:Two of|two of)')],
    [3, re.compile('(?:Three of|three of)')],
    [4, re.compile('(?:Four of|four of)')],
    [5, re.compile('(?:Five of|five of)')],
]

def filterPrereqContainer(tag):
    return tag.name == 'p' and len(tag.contents) and RE_STRING_PREREQ.match(tag.contents[0].get_text())

def filterCoreqContainer(tag):
    return tag.name == 'p' and len(tag.contents) and RE_STRING_COREQ.match(tag.contents[0].get_text())

def checkCourseNotOffered(container):
    return any(RE_STRING_NOOFFER.search(content.get_text()) for content in container.contents)

def checkNumberOfCoursesRequired(line):
    for NUM_CRIT in RE_STRING_REQUIRED_COURSES:
        if NUM_CRIT[1].search(line): return NUM_CRIT[0]
    return -1 # if no match, this line is not a prereq indicator

def getCoursePrereqs(courseKey, container):
    prereqGroups = [] # collect prereqs
    requiredCourses = 0 # number of courses required in the group
    prereqGroupCounter = -1

    for currLine in container:
        # get number of courses required for this prereq group
        coursesRequired = checkNumberOfCoursesRequired(currLine.get_text())

        # add to prereq list as necessary
        if coursesRequired != -1: # if an indicator is given
            requiredCourses = coursesRequired # save the number of required corses
            prereqGroupCounter += 1 # increment the group number
            continue
        elif prereqGroupCounter == -1: # if no indicator but its the first line
            requiredCourses = 0
            prereqGroupCounter += 1
            continue

        # if its not a link or no indicator yet (weird use case)
        if prereqGroupCounter == -1 or currLine.name != 'a': continue
        # add as a prereq
        prereqGroups.append({
            'group': prereqGroupCounter,
            'numRequired': requiredCourses,
            'prereq': currLine.get_text().strip().replace(" ", "-").lower(),
            'dependent': courseKey,
        })

    return prereqGroups

def getCourseCoreqs(container):
    return [coreq.get_text().strip() for coreq in container.find_all('a')]

def findCourseDependencies(allCoursesEncountered, allCourseInfo, dept: str, courseNum: str):
    # if already have data, don't repeat the computation
    courseKey = (dept+'-'+courseNum).lower()
    if courseKey in allCourseInfo: return allCourseInfo[courseKey]

    # add to list of courses encountered so far
    courseInfo = { 'dept': dept, 'courseNum': courseNum,'status': 'OFFERED',  'prereqs': [], 'coreqs': []}
    newCoursesEncountered = [*allCoursesEncountered, courseKey]

    try:
        # get course info
        driver.get(generateUrl('COURSES', dept, courseNum))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        content_container = soup.find('div', class_=re.compile('content expand'))

        # check if course is offered
        if checkCourseNotOffered(content_container):
            courseInfo['status'] = 'NOT_OFFERED'
            return courseInfo

        # get prereq containers and coreq containers, if any
        prereqContainer = content_container.find_all(filterPrereqContainer)
        coreqContainer = content_container.find_all(filterCoreqContainer)

        if not len(prereqContainer) and not len(coreqContainer):
            # course has no prereqs/coreqs, end here
            print(f'DEBUG (scrape_course): course {dept} {courseNum} has no prereqs/coreqs')
            return courseInfo
        
        # get list of prereqs and coreqs
        prereqs = [] if not len(prereqContainer) else getCoursePrereqs(courseKey, prereqContainer[0]) 
        coreqs = [] if not len(coreqContainer) else getCourseCoreqs(coreqContainer[0]) 
        
        # save the courseinfo
        courseInfo['prereqs'] = prereqs
        courseInfo['coreqs'] = coreqs
        allCourseInfo[courseKey] = copy.deepcopy(courseInfo)

        # recurse here for prereqs
        if len(prereqs):
            for idx, p in enumerate(prereqs):
                pr = p['prereq'].split('-')
                prInfo = findCourseDependencies(newCoursesEncountered, allCourseInfo, pr[0], pr[1])
                courseInfo['prereqs'][idx]['prereqInfo'] = prInfo
        else:
            print(f'DEBUG (scrape_course): no prereqs found for {dept} {courseNum}')

        # don't need to recurse for coreqs

    except Exception as e:
        print('ERROR ->>> could not find dependency for', f'{dept} {courseNum}',  '{}'.format(e))
        traceback.print_exc()
    finally:
        return courseInfo

def scrapeCourseInformation(dept: str, courseNum: str):
    allCourseInfo = {}
    mainCourseInfo = {}

    try:
        # do this initially to test connection
        driver.get(generateUrl('COURSES', dept, courseNum))
        # start finding dependencies
        mainCourseInfo = findCourseDependencies([], allCourseInfo, dept, courseNum)
    except Exception as e:
        print('ERROR ->>> could not scrape course page. {}'.format(e))
        traceback.print_exc()
        raise
    finally:
        print(allCourseInfo)
        return mainCourseInfo
